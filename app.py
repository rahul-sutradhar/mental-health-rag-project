"""
===============================================================================
🎓 MINDMATE AI: FASTAPI BACKEND SERVER
===============================================================================
This module replaces Flask with FastAPI, providing:
  1. SQLAlchemy Models for Users, Threads, and Messages
  2. Database-agnostic support (SQLite locally, Supabase PostgreSQL in prod)
  3. Starlette Session Middleware for user login sessions
  4. Compatibility wrapper for Flask's Jinja2 template syntax
  5. API endpoints for Auth (with Argon2), Thread Management, and RAG Chat
===============================================================================
"""

import os, sys
import datetime
from typing import Optional
import json
from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime, desc
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# Import our custom Mistral chatbot engine
import bot

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# ==============================================================================
# 🗄️ DATABASE CONFIGURATION (SQLAlchemy)
# ==============================================================================

# Default to SQLite locally, but use Supabase/PostgreSQL if DATABASE_URL is set in prod
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./mindmate.db"

# Setup SQLAlchemy engine (SQLite requires check_same_thread=False parameter)
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # Fix Render/Heroku postgresql:// schemes if needed
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==============================================================================
# 📊 DATABASE MODELS
# ==============================================================================

class User(Base):
    """User account details for authentication and tokens tracking."""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    user_type = Column(String, nullable=False) # 'user', 'specialist', 'admin', 'master_admin'
    tokens = Column(Integer, default=100)      # Welcome tokens bonus
    full_name = Column(String, nullable=True)
    specialist_status = Column(String(50), default="none") # 'none', 'pending', 'approved', 'rejected'
    specialist_details = Column(Text, nullable=True) # Qualifications / certification details

class ChatThread(Base):
    """ChatGPT-like chat threads belonging to a user."""
    __tablename__ = "chat_threads"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, default="New Chat")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class ChatMessage(Base):
    """Indiviual chat messages within a thread."""
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(Integer, ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False)
    sender = Column(String, nullable=False) # 'user' or 'bot'
    message = Column(Text, nullable=False)
    emotion = Column(String, nullable=True) # Classified emotion
    risk_level = Column(String, nullable=True) # Risk evaluation
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class SpecialistBooking(Base):
    """Specialist booking details."""
    __tablename__ = "specialist_bookings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    specialist_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    session_type = Column(String, nullable=False) # 'Text Chat' or 'Video Call'
    date = Column(String, nullable=False)
    time = Column(String, nullable=False)
    status = Column(String, default="pending") # 'pending', 'approved', 'assigned', 'completed'
    reason = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    is_calling = Column(Integer, default=0) # 0=idle, 1=calling, 2=accepted, 3=declined
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class SpecialistMessage(Base):
    """Messages exchanged between a user and specialist inside a booking thread."""
    __tablename__ = "specialist_messages"
    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("specialist_bookings.id", ondelete="CASCADE"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

# Create database tables
Base.metadata.create_all(bind=engine)

from sqlalchemy import text
def upgrade_db_schema():
    # If using sqlite, check if full_name column exists and add it if missing
    db = SessionLocal()
    try:
        db.execute(text("SELECT full_name FROM users LIMIT 1"))
    except Exception:
        db.rollback()
        try:
            print("Upgrading database schema: adding full_name to users...")
            db.execute(text("ALTER TABLE users ADD COLUMN full_name VARCHAR DEFAULT ''"))
            db.commit()
        except Exception as e:
            print(f"⚠️ Error upgrading database schema: {e}")
            db.rollback()
    finally:
        db.close()

    # Check and add specialist_status column to users if missing
    db = SessionLocal()
    try:
        db.execute(text("SELECT specialist_status FROM users LIMIT 1"))
    except Exception:
        db.rollback()
        try:
            print("Upgrading database schema: adding specialist_status to users...")
            db.execute(text("ALTER TABLE users ADD COLUMN specialist_status VARCHAR(50) DEFAULT 'none'"))
            db.commit()
        except Exception as e:
            print(f"⚠️ Error upgrading database (specialist_status): {e}")
            db.rollback()
    finally:
        db.close()

    # Check and add specialist_details column to users if missing
    db = SessionLocal()
    try:
        db.execute(text("SELECT specialist_details FROM users LIMIT 1"))
    except Exception:
        db.rollback()
        try:
            print("Upgrading database schema: adding specialist_details to users...")
            db.execute(text("ALTER TABLE users ADD COLUMN specialist_details TEXT"))
            db.commit()
        except Exception as e:
            print(f"⚠️ Error upgrading database (specialist_details): {e}")
            db.rollback()
    finally:
        db.close()

    # Check and add is_calling column to specialist_bookings if missing
    db = SessionLocal()
    try:
        db.execute(text("SELECT is_calling FROM specialist_bookings LIMIT 1"))
    except Exception:
        db.rollback()
        try:
            print("Upgrading database schema: adding is_calling to specialist_bookings...")
            db.execute(text("ALTER TABLE specialist_bookings ADD COLUMN is_calling INTEGER DEFAULT 0"))
            db.commit()
        except Exception as e:
            print(f"⚠️ Error upgrading database (is_calling): {e}")
            db.rollback()
    finally:
        db.close()

def seed_default_users():
    db = SessionLocal()
    try:
        default_accounts = [
            {"email": "user@mindmate.com", "password": "user123", "user_type": "user", "full_name": "Normal User"},
            {"email": "specialist@mindmate.com", "password": "specialist123", "user_type": "specialist", "full_name": "Dr. Sarah Johnson"},
            {"email": "admin@mindmate.com", "password": "admin123", "user_type": "admin", "full_name": "App Admin"},
            {"email": "masteradmin@mindmate.com", "password": "master123", "user_type": "master_admin", "full_name": "Master Admin"}
        ]
        for acc in default_accounts:
            existing = db.query(User).filter(User.email == acc["email"]).first()
            if not existing:
                hashed_pw = ph.hash(acc["password"])
                user = User(
                    email=acc["email"], 
                    password=hashed_pw, 
                    user_type=acc["user_type"], 
                    full_name=acc["full_name"],
                    tokens=100
                )
                db.add(user)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"⚠️ Error seeding users: {e}")
    finally:
        db.close()

from contextlib import asynccontextmanager

# Database Session Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Global vector store instance for RAG
vector_store = None

@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """Builds or loads the RAG vector index on startup."""
    global vector_store
    vector_store = bot.initialize_rag()
    upgrade_db_schema()
    seed_default_users()
    yield

# ==============================================================================
# 🚀 FASTAPI APP & INTERFACE CONFIGURATIONS
# ==============================================================================

app = FastAPI(title="MindMate AI — Full Stack Wellness Companion", lifespan=lifespan)

# Enable Cross-Origin Resource Sharing (CORS)
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex="https://.*\\.github\\.io|http://localhost:.*|http://127\\.0\\.0\\.1:.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health_check():
    """Simple health check endpoint to keep the Render backend awake."""
    return {"status": "healthy", "timestamp": datetime.datetime.now(datetime.UTC).isoformat()}


# Starlette Session Middleware (cookie-based login sessions fallback)
# Generates a random session secret key if not set in .env
SESSION_SECRET = os.getenv("SESSION_SECRET", os.urandom(24).hex())

# In production (cross-origin decoupled hosting), SameSite must be None and secure (https_only) must be True
# to allow session cookies across the github.io and onrender.com domains
IS_TESTING = "pytest" in sys.modules or os.getenv("TESTING") is not None
IS_PROD = (os.getenv("DATABASE_URL") is not None or os.getenv("RENDER") is not None) and not IS_TESTING
if IS_PROD:
    app.add_middleware(
        SessionMiddleware, 
        secret_key=SESSION_SECRET,
        same_site="none",
        https_only=True
    )
else:
    app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

# Mount frontend static directory (CSS, JS, manifest) if it exists (local development fallback)
if os.path.exists("frontend/static"):
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Jinja2 Templates Directory (development fallback)
templates = Jinja2Templates(directory="templates")

# Helper to resolve user session/header authorization stateless
def get_user_id(request: Request) -> int:
    user_id_raw = request.headers.get("X-User-Id")
    if user_id_raw:
        try:
            return int(user_id_raw)
        except ValueError:
            pass
    user_id = request.session.get("user_id")
    if user_id is not None:
        return user_id
    raise HTTPException(status_code=401, detail="Unauthorized")

# Password Hasher (Argon2)
ph = PasswordHasher()


# ==============================================================================
# 🎨 JINJA2 TEMPLATE HELPERS (Flask Compatibility)
# ==============================================================================

def make_url_for(request: Request):
    """
    Returns a custom url_for wrapper that maps Flask-style template variables
    url_for('static', filename='...') to Starlette's url_for('static', path='...').
    This avoids editing 19 HTML template files.
    """
    def url_for_wrapper(name: str, **kwargs):
        if name == "static":
            path = kwargs.get("filename") or kwargs.get("path")
            return str(request.url_for(name, path=path))
        return str(request.url_for(name, **kwargs))
    return url_for_wrapper


def render(request: Request, template_name: str, context: Optional[dict] = None):
    """Injects request and the custom url_for wrapper into Jinja2 contexts."""
    if context is None:
        context = {}
    ctx = {
        "request": request,
        "url_for": make_url_for(request),
        **context
    }
    return templates.TemplateResponse(
        name=template_name,
        context=ctx,
        request=request
    )


# ==============================================================================
# 📂 WEB PAGE ROUTES (Served as HTML)
# ==============================================================================

if os.path.exists("templates"):
    @app.get("/", name="index")
    @app.get("/index.html", name="index")
    async def index_page(request: Request):
        return render(request, "index.html")

    @app.get("/about.html", name="about")
    async def about_page(request: Request):
        return render(request, "about.html")

    @app.get("/login.html", name="login_page")
    async def login_page(request: Request):
        return render(request, "login.html")

    @app.get("/choose-support.html", name="choose_support")
    async def choose_support_page(request: Request):
        if "user_id" not in request.session:
            return RedirectResponse(url="/login.html", status_code=status.HTTP_303_SEE_OTHER)
        return render(request, "choose-support.html")

    @app.get("/ai-chat.html", name="ai_chat")
    async def ai_chat_page(request: Request):
        if "user_id" not in request.session:
            return RedirectResponse(url="/login.html", status_code=status.HTTP_303_SEE_OTHER)
        return render(request, "ai-chat.html")

    @app.get("/specialists.html", name="specialists")
    async def specialists_page(request: Request):
        return render(request, "specialists.html")

    @app.get("/assessment.html", name="assessment")
    async def assessment_page(request: Request):
        return render(request, "assessment.html")

    @app.get("/specialist-dashboard.html", name="specialist_dash")
    async def specialist_dashboard_page(request: Request):
        if "user_id" not in request.session:
            return RedirectResponse(url="/login.html", status_code=status.HTTP_303_SEE_OTHER)
        if request.session.get("user_type") != "specialist":
            return RedirectResponse(url="/login.html", status_code=status.HTTP_303_SEE_OTHER)
        return render(request, "specialist-dashboard.html")

    @app.get("/specialist-console.html", name="specialist_console")
    async def specialist_console_page(request: Request):
        if "user_id" not in request.session:
            return RedirectResponse(url="/login.html", status_code=status.HTTP_303_SEE_OTHER)
        if request.session.get("user_type") != "specialist":
            return RedirectResponse(url="/login.html", status_code=status.HTTP_303_SEE_OTHER)
        return render(request, "specialist-console.html")

    @app.get("/admin-dashboard.html", name="admin_dashboard")
    async def admin_dashboard_page(request: Request):
        if "user_id" not in request.session:
            return RedirectResponse(url="/login.html", status_code=status.HTTP_303_SEE_OTHER)
        if request.session.get("user_type") not in ["admin", "master_admin"]:
            return RedirectResponse(url="/login.html", status_code=status.HTTP_303_SEE_OTHER)
        return render(request, "admin-dashboard.html")

    @app.get("/dashboard.html", name="dashboard")
    async def dashboard_page(request: Request):
        if "user_id" not in request.session:
            return RedirectResponse(url="/login.html", status_code=status.HTTP_303_SEE_OTHER)
        return render(request, "dashboard.html")

    @app.get("/store.html", name="store")
    async def store_page(request: Request):
        return render(request, "store.html")

    @app.get("/booking.html", name="booking")
    async def booking_page(request: Request):
        if "user_id" not in request.session:
            return RedirectResponse(url="/login.html", status_code=status.HTTP_303_SEE_OTHER)
        return render(request, "booking.html")

    @app.get("/chat-room.html", name="chat_room")
    async def chat_room_page(request: Request):
        if "user_id" not in request.session:
            return RedirectResponse(url="/login.html", status_code=status.HTTP_303_SEE_OTHER)
        return render(request, "chat-room.html")

    @app.get("/specialist-profile.html", name="specialist_profile")
    async def specialist_profile_page(request: Request):
        return render(request, "specialist-profile.html")

    @app.get("/video-call.html", name="video_call")
    async def video_call_page(request: Request):
        if "user_id" not in request.session:
            return RedirectResponse(url="/login.html", status_code=status.HTTP_303_SEE_OTHER)
        return render(request, "video-call.html")

    @app.get("/contact.html", name="contact")
    async def contact_page(request: Request):
        return render(request, "contact.html")

    @app.get("/faq.html", name="faq")
    async def faq_page(request: Request):
        return render(request, "faq.html")

    @app.get("/privacy.html", name="privacy")
    async def privacy_page(request: Request):
        return render(request, "privacy.html")

    @app.get("/terms.html", name="terms")
    async def terms_page(request: Request):
        return render(request, "terms.html")

    @app.get("/404.html", name="not_found_page")
    async def not_found_page(request: Request):
        return render(request, "404.html")
else:
    @app.get("/")
    async def root():
        return {
            "status": "healthy",
            "message": "MindMate AI Backend API is running.",
            "version": "1.0.0"
        }



# ==============================================================================
# 🔑 AUTHENTICATION ENDPOINTS (Argon2)
# ==============================================================================

@app.post("/api/auth")
async def auth_handler(request: Request, db: Session = Depends(get_db)):
    """Handles signup and login. Stores password hashes using Argon2."""
    data = await request.json()
    if not data:
        return JSONResponse({'success': False, 'message': 'Invalid request.'}, status_code=400)

    email = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()
    action = data.get('action', '').strip() # 'login' or 'signup'
    user_type = data.get('user_type', 'user').strip()

    if not email or not password or action not in ['login', 'signup']:
        return JSONResponse({'success': False, 'message': 'Please fill all required fields.'}, status_code=400)

    if action == 'signup':
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            return JSONResponse({'success': False, 'message': 'Email already exists.'}, status_code=400)
            
        try:
            # Secure password hashing with Argon2
            hashed_pw = ph.hash(password)
            
            db_user_type = user_type
            db_specialist_status = "none"
            db_specialist_details = None
            if user_type == "specialist":
                db_user_type = "user"
                db_specialist_status = "pending"
                db_specialist_details = data.get("specialist_details", "").strip()

            new_user = User(
                email=email, 
                password=hashed_pw, 
                user_type=db_user_type,
                full_name=email.split('@')[0].capitalize(),
                specialist_status=db_specialist_status,
                specialist_details=db_specialist_details
            )
            db.add(new_user)
            db.commit()
            db.refresh(new_user)

            # Establish user session
            request.session['user_id'] = new_user.id
            request.session['email'] = new_user.email
            request.session['user_type'] = new_user.user_type

            if user_type == "specialist":
                redirect_url = "dashboard.html"
            elif db_user_type in ["admin", "master_admin"]:
                redirect_url = "admin-dashboard.html"
            else:
                redirect_url = "choose-support.html"

            return {
                'success': True, 
                'message': 'Account created successfully!', 
                'redirect': redirect_url,
                'user_id': new_user.id,
                'email': new_user.email,
                'tokens': new_user.tokens,
                'user_type': new_user.user_type,
                'specialist_status': new_user.specialist_status
            }
        except Exception as e:
            db.rollback()
            return JSONResponse({'success': False, 'message': f'Server error: {str(e)}'}, status_code=500)

    # Logic for login
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return JSONResponse({'success': False, 'message': 'Invalid credentials.'}, status_code=401)

    try:
        # Secure password verification with Argon2
        ph.verify(user.password, password)
        
        # Establish user session
        request.session['user_id'] = user.id
        request.session['email'] = user.email
        request.session['user_type'] = user.user_type

        if user.user_type == "specialist":
            redirect_url = "specialist-console.html"
        elif user.user_type in ["admin", "master_admin"]:
            redirect_url = "admin-dashboard.html"
        else:
            redirect_url = "choose-support.html"

        return {
            'success': True, 
            'message': 'Logged in successfully!', 
            'redirect': redirect_url,
            'user_id': user.id,
            'email': user.email,
            'tokens': user.tokens,
            'user_type': user.user_type,
            'specialist_status': user.specialist_status
        }
    except VerifyMismatchError:
        return JSONResponse({'success': False, 'message': 'Invalid credentials.'}, status_code=401)

@app.get("/api/logout", name="logout")
async def logout_handler(request: Request):
    """Clears user session cookies."""
    request.session.clear()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

import httpx
@app.post("/api/auth/google")
async def google_auth_handler(request: Request, db: Session = Depends(get_db)):
    """Authenticates users via Google ID tokens (includes dev mock support)."""
    data = await request.json()
    token = data.get("credential") or data.get("id_token")
    if not token:
        return JSONResponse({'success': False, 'message': 'Google credential token is missing.'}, status_code=400)
        
    email = None
    name = "Google User"
    
    # 1. Dev mock simulation check
    if token.startswith("mock:"):
        email = token.replace("mock:", "").strip().lower()
        name = email.split('@')[0].capitalize()
    else:
        # 2. Call Google's tokeninfo verification endpoint
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={token}")
                if res.status_code == 200:
                    payload = res.json()
                    email = payload.get("email")
                    name = payload.get("name", name)
                else:
                    return JSONResponse({'success': False, 'message': 'Invalid Google ID token.'}, status_code=400)
        except Exception as e:
            return JSONResponse({'success': False, 'message': f'Failed to contact Google verification server: {str(e)}'}, status_code=500)
            
    if not email:
        return JSONResponse({'success': False, 'message': 'Could not retrieve email from Google credential.'}, status_code=400)
        
    # Check if user exists
    user = db.query(User).filter(User.email == email).first()
    if not user:
        # Create a new user with google authentication placeholder
        try:
            user = User(
                email=email,
                password="google-auth-placeholder",
                user_type="user",
                full_name=name
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        except Exception as e:
            db.rollback()
            return JSONResponse({'success': False, 'message': f'Error registering Google user: {str(e)}'}, status_code=500)
            
    # Establish session
    request.session['user_id'] = user.id
    request.session['email'] = user.email
    request.session['user_type'] = user.user_type
    
    # Determine redirect
    if user.user_type == "specialist":
        redirect_url = "specialist-console.html"
    elif user.user_type in ["admin", "master_admin"]:
        redirect_url = "admin-dashboard.html"
    else:
        redirect_url = "choose-support.html"
        
    return {
        'success': True,
        'message': 'Logged in via Google successfully!',
        'redirect': redirect_url,
        'user_id': user.id,
        'email': user.email,
        'tokens': user.tokens,
        'user_type': user.user_type,
        'specialist_status': user.specialist_status
    }


@app.get("/api/session")
async def session_handler(request: Request, db: Session = Depends(get_db)):
    """Retrieves current user login state details."""
    if 'user_id' not in request.session:
        return {'logged_in': False}
        
    user_id = request.session.get('user_id')
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {'logged_in': False}
        
    return {
        'logged_in': True,
        'user_id': user.id,
        'email': user.email,
        'user_type': user.user_type,
        'full_name': user.full_name or user.email.split("@")[0].capitalize(),
        'tokens': user.tokens,
        'specialist_status': user.specialist_status
    }


# ==============================================================================
# 💬 CHAT THREADS MANAGEMENT ENDPOINTS
# ==============================================================================

@app.get("/api/chat/threads")
async def get_threads(request: Request, db: Session = Depends(get_db)):
    """Retrieves all chat threads for the logged-in user."""
    user_id = get_user_id(request)
    threads = db.query(ChatThread).filter(ChatThread.user_id == user_id).order_by(desc(ChatThread.created_at)).all()
    
    return [
        {
            "id": t.id,
            "title": t.title,
            "created_at": t.created_at.strftime("%Y-%m-%d %H:%M:%S")
        } for t in threads
    ]


@app.post("/api/chat/threads")
async def create_thread(request: Request, db: Session = Depends(get_db)):
    """Creates a new chat thread for the logged-in user."""
    user_id = get_user_id(request)
    
    try:
        new_thread = ChatThread(user_id=user_id, title="New Chat")
        db.add(new_thread)
        db.commit()
        db.refresh(new_thread)
        
        return {
            "id": new_thread.id,
            "title": new_thread.title,
            "created_at": new_thread.created_at.strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/chat/threads/{thread_id}")
async def delete_thread(thread_id: int, request: Request, db: Session = Depends(get_db)):
    """Deletes a chat thread and all its associated messages."""
    user_id = get_user_id(request)
    thread = db.query(ChatThread).filter(ChatThread.id == thread_id, ChatThread.user_id == user_id).first()
    
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
        
    try:
        db.delete(thread)
        db.commit()
        return {"success": True, "message": "Thread deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chat/history/{thread_id}")
async def get_thread_history(thread_id: int, request: Request, db: Session = Depends(get_db)):
    """Retrieves all messages stored in a specific chat thread."""
    user_id = get_user_id(request)
    # Secure validation: Check that the thread belongs to the current user
    thread = db.query(ChatThread).filter(ChatThread.id == thread_id, ChatThread.user_id == user_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
        
    messages = db.query(ChatMessage).filter(ChatMessage.thread_id == thread_id).order_by(ChatMessage.timestamp).all()
    
    return [
        {
            "id": m.id,
            "sender": m.sender,
            "message": m.message,
            "emotion": m.emotion,
            "risk": m.risk_level,
            "timestamp": m.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        } for m in messages
    ]


# ==============================================================================
# 🤖 ADVANCED RAG CHATBOT ENDPOINT (Mistral + Cosine Similarity + Reranker)
# ==============================================================================

@app.post("/api/chat")
async def chat_handler(request: Request, db: Session = Depends(get_db)):
    """
    RAG chat processor: fetches message context (Vector Search -> Reranker),
    assembles chat memory from DB, and streams the Mistral Large response
    token-by-token. Logs interactions and updates thread titles dynamically.
    """
    user_id = get_user_id(request)
    data = await request.json()
    if not data:
        raise HTTPException(status_code=400, detail="Invalid request payload")
        
    user_input = data.get('message', '').strip()
    thread_id = data.get('thread_id')
    
    if not user_input:
        raise HTTPException(status_code=400, detail="Message is empty")
        
    # 1. Fetch or create dynamic thread if none is provided
    thread = None
    if thread_id:
        thread = db.query(ChatThread).filter(ChatThread.id == thread_id, ChatThread.user_id == user_id).first()
        
    if not thread:
        thread = ChatThread(user_id=user_id, title="New Chat")
        db.add(thread)
        db.commit()
        db.refresh(thread)
        thread_id = thread.id
        
    # 2. Retrieve recent message history in this thread for model memory (limit 6)
    history_records = db.query(ChatMessage).filter(ChatMessage.thread_id == thread_id).order_by(desc(ChatMessage.timestamp)).limit(6).all()
    # Reverse to keep chronological order
    history_records.reverse()
    
    chat_history = [
        {"sender": m.sender, "message": m.message} for m in history_records
    ]
    
    # 3. Retrieve relevant context chunks using RAG (Vector Similarity + Reranking)
    context_chunks = []
    if vector_store and vector_store.documents:
        top_matches = vector_store.similarity_search(user_input, k=10)
        candidate_chunks = [match[0] for match in top_matches]
        context_chunks = await bot.rerank_documents(query=user_input, documents=candidate_chunks, k=3)
        
    async def event_generator():
        # A. Stream response tokens in real-time
        full_reply = []
        async for chunk in bot.get_mistral_chat_stream(user_input, chat_history, context_chunks):
            full_reply.append(chunk)
            yield chunk
            
        full_reply_text = "".join(full_reply)
        
        # B. Rapidly classify emotion & risk
        classification = bot.classify_message(user_input)
        emotion = classification.get("emotion", "sad")
        risk_level = classification.get("risk", "NORMAL")
        confidence = classification.get("confidence", "75%")
        
        # C. Save interaction to database (using a dedicated session to prevent async race conditions)
        new_title = thread.title
        total_messages = 0
        try:
            db_session = SessionLocal()
            total_messages = db_session.query(ChatMessage).filter(ChatMessage.thread_id == thread_id).count()
            
            user_msg_db = ChatMessage(thread_id=thread_id, sender='user', message=user_input)
            bot_msg_db = ChatMessage(
                thread_id=thread_id, 
                sender='bot', 
                message=full_reply_text, 
                emotion=emotion, 
                risk_level=risk_level
            )
            db_session.add(user_msg_db)
            db_session.add(bot_msg_db)
            
            # D. Dynamically update thread title if this was the first user message
            if total_messages == 0:
                new_title = bot.generate_thread_title(user_input)
                t_db = db_session.query(ChatThread).filter(ChatThread.id == thread_id).first()
                if t_db:
                    t_db.title = new_title
                    
            db_session.commit()
            db_session.close()
        except Exception as e:
            print(f"⚠️ Error saving messages to database: {e}")
            
        # E. Yield the metadata payload at the very end
        metadata = {
            "emotion": emotion,
            "risk": risk_level,
            "confidence": confidence,
            "thread_id": thread_id,
            "thread_title": new_title if total_messages == 0 else None
        }
        yield f"\n[METADATA] {json.dumps(metadata)}"

    return StreamingResponse(event_generator(), media_type="text/plain")


    # ==============================================================================
# 🩺 SPECIALIST & BOOKING API ENDPOINTS
# ==============================================================================

@app.get("/api/specialists")
async def get_specialists(db: Session = Depends(get_db)):
    """Fetch all users marked as specialists."""
    specialists = db.query(User).filter(User.user_type == "specialist").all()
    return [
        {
            "id": s.id,
            "email": s.email,
            "full_name": s.full_name or s.email.split("@")[0].capitalize(),
            "tokens": s.tokens
        } for s in specialists
    ]

@app.post("/api/user/bookings")
async def create_user_booking(request: Request, db: Session = Depends(get_db)):
    """Deduct tokens and book a chat/video session with a specialist."""
    user_id = get_user_id(request)
    data = await request.json()
    
    specialist_id = data.get("specialist_id")
    session_type = data.get("session_type", "Text Chat")
    date = data.get("date")
    time = data.get("time")
    reason = data.get("reason", "")
    notes = data.get("notes", "")
    
    cost = 100 if session_type == "Video Call" else 50
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.tokens < cost:
        raise HTTPException(status_code=400, detail="Insufficient tokens")
        
    user.tokens -= cost
    
    booking = SpecialistBooking(
        user_id=user_id,
        specialist_id=specialist_id,
        session_type=session_type,
        date=date,
        time=time,
        status="assigned" if specialist_id else "pending",
        reason=reason,
        notes=notes
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return {"success": True, "booking_id": booking.id, "remaining_tokens": user.tokens}

@app.get("/api/user/bookings")
async def get_user_bookings(request: Request, db: Session = Depends(get_db)):
    """Fetch all upcoming and past bookings for the logged-in user."""
    user_id = get_user_id(request)
    bookings = db.query(SpecialistBooking).filter(SpecialistBooking.user_id == user_id).order_by(desc(SpecialistBooking.created_at)).all()
    
    results = []
    for b in bookings:
        spec = db.query(User).filter(User.id == b.specialist_id).first() if b.specialist_id else None
        results.append({
            "id": b.id,
            "specialist_id": b.specialist_id,
            "specialist_name": spec.full_name if spec else "Unassigned",
            "session_type": b.session_type,
            "date": b.date,
            "time": b.time,
            "status": b.status,
            "reason": b.reason,
            "notes": b.notes
        })
    return results

@app.get("/api/specialist/bookings")
async def get_specialist_bookings(request: Request, db: Session = Depends(get_db)):
    """Fetch all bookings assigned to the logged-in specialist."""
    user_id = get_user_id(request)
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.user_type != "specialist":
        raise HTTPException(status_code=403, detail="Forbidden")
        
    bookings = db.query(SpecialistBooking).filter(SpecialistBooking.specialist_id == user_id).order_by(desc(SpecialistBooking.created_at)).all()
    
    results = []
    for b in bookings:
        client = db.query(User).filter(User.id == b.user_id).first()
        results.append({
            "id": b.id,
            "client_email": client.email if client else "Unknown Client",
            "client_name": client.full_name if client else "Unknown Client",
            "session_type": b.session_type,
            "date": b.date,
            "time": b.time,
            "status": b.status,
            "reason": b.reason,
            "notes": b.notes
        })
    return results

@app.put("/api/specialist/bookings/{booking_id}/status")
async def update_booking_status(booking_id: int, request: Request, db: Session = Depends(get_db)):
    """Let the specialist complete or approve a booking session."""
    user_id = get_user_id(request)
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.user_type != "specialist":
         raise HTTPException(status_code=403, detail="Forbidden")
         
    booking = db.query(SpecialistBooking).filter(SpecialistBooking.id == booking_id, SpecialistBooking.specialist_id == user_id).first()
    if not booking:
         raise HTTPException(status_code=404, detail="Booking not found")
         
    data = await request.json()
    status_val = data.get("status")
    if status_val not in ["approved", "completed", "cancelled"]:
         raise HTTPException(status_code=400, detail="Invalid status")
         
    booking.status = status_val
    db.commit()
    return {"success": True, "status": booking.status}

@app.get("/api/bookings/{booking_id}/call-state")
async def get_call_state(booking_id: int, request: Request, db: Session = Depends(get_db)):
    """Check the call state of a booking session."""
    user_id = get_user_id(request)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    booking = db.query(SpecialistBooking).filter(SpecialistBooking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
        
    if booking.user_id != user_id and booking.specialist_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    partner_name = ""
    partner_avatar = "https://i.pravatar.cc/150?img=47"
    if user.user_type == "specialist":
        partner = db.query(User).filter(User.id == booking.user_id).first()
        partner_name = partner.full_name if partner else "Client"
    else:
        partner = db.query(User).filter(User.id == booking.specialist_id).first()
        partner_name = partner.full_name if partner else "Specialist"
        
    return {
        "booking_id": booking.id,
        "is_calling": booking.is_calling,
        "partner_name": partner_name,
        "partner_avatar": partner_avatar,
        "session_type": booking.session_type
    }

@app.put("/api/bookings/{booking_id}/call-state")
async def update_call_state(booking_id: int, request: Request, db: Session = Depends(get_db)):
    """Update the call state of a booking session."""
    user_id = get_user_id(request)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    booking = db.query(SpecialistBooking).filter(SpecialistBooking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
        
    if booking.user_id != user_id and booking.specialist_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    data = await request.json()
    is_calling_val = data.get("is_calling")
    if is_calling_val is None or is_calling_val not in [0, 1, 2, 3]:
        raise HTTPException(status_code=400, detail="Invalid call state")
        
    booking.is_calling = is_calling_val
    db.commit()
    return {"success": True, "is_calling": booking.is_calling}

@app.get("/api/bookings/{booking_id}/messages")
async def get_booking_messages(booking_id: int, request: Request, db: Session = Depends(get_db)):
    """Retrieve chat history for a specialist booking thread."""
    user_id = get_user_id(request)
    booking = db.query(SpecialistBooking).filter(SpecialistBooking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
        
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    if user_id != booking.user_id and user_id != booking.specialist_id and current_user.user_type not in ["admin", "master_admin"]:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    messages = db.query(SpecialistMessage).filter(SpecialistMessage.booking_id == booking_id).order_by(SpecialistMessage.timestamp).all()
    
    return [
        {
            "id": m.id,
            "sender_id": m.sender_id,
            "message": m.message,
            "timestamp": m.timestamp.isoformat()
        } for m in messages
    ]

@app.post("/api/bookings/{booking_id}/messages")
async def send_booking_message(booking_id: int, request: Request, db: Session = Depends(get_db)):
    """Post a message inside a booking thread."""
    user_id = get_user_id(request)
    booking = db.query(SpecialistBooking).filter(SpecialistBooking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
        
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    if user_id != booking.user_id and user_id != booking.specialist_id:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    data = await request.json()
    msg_text = data.get("message", "").strip()
    if not msg_text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
        
    new_msg = SpecialistMessage(
        booking_id=booking_id,
        sender_id=user_id,
        message=msg_text
    )
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)
    return {
        "id": new_msg.id,
        "sender_id": new_msg.sender_id,
        "message": new_msg.message,
        "timestamp": new_msg.timestamp.isoformat()
    }


# ==============================================================================
# 👑 ADMIN PANEL & ROLE CONTROLS API ENDPOINTS
# ==============================================================================

def verify_admin_action(actor: User, target_user: User, action_type: str, new_role: str = None) -> bool:
    """
    Validates role permissions for admin actions:
    action_type can be: 'delete', 'update_role', 'reset_password'
    """
    # No admin or master admin can delete themselves or change/demote their own role
    if actor.id == target_user.id and action_type in ["delete", "update_role"]:
        return False

    # Master Admin rules:
    if actor.user_type == "master_admin":
        # Master Admin can change anything except demoting/modifying another master admin
        if target_user.user_type == "master_admin" and actor.id != target_user.id:
            return False
        return True

    # Admin rules:
    if actor.user_type == "admin":
        # Cannot demote or change Master Admin (read-only)
        if target_user.user_type == "master_admin":
            return False
        
        if action_type == "update_role":
            # Admin can convert user <-> specialist
            # Cannot promote anyone to admin or master admin
            if new_role in ["admin", "master_admin"]:
                return False
            # Cannot demote other Admin or Self
            if target_user.user_type in ["admin", "master_admin"]:
                return False
            return True
            
        elif action_type == "reset_password":
            # Admin can reset User, Specialist, and Self
            if target_user.user_type == "admin" and actor.id != target_user.id:
                return False # Cannot reset other admin
            return True
            
        elif action_type == "delete":
            # Admin cannot delete other Admins, Self, or Master Admins
            if target_user.user_type in ["admin", "master_admin"]:
                return False
            return True
            
    return False

@app.get("/api/admin/users")
async def admin_get_users(request: Request, db: Session = Depends(get_db)):
    """Fetch all users registered on the platform."""
    user_id = get_user_id(request)
    actor = db.query(User).filter(User.id == user_id).first()
    if not actor or actor.user_type not in ["admin", "master_admin"]:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    users = db.query(User).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "user_type": u.user_type,
            "full_name": u.full_name or u.email.split("@")[0].capitalize(),
            "tokens": u.tokens
        } for u in users
    ]

@app.post("/api/admin/users")
async def admin_create_user(request: Request, db: Session = Depends(get_db)):
    """Admin-only creation of User, Specialist, or Admin (within rules)."""
    user_id = get_user_id(request)
    actor = db.query(User).filter(User.id == user_id).first()
    if not actor or actor.user_type not in ["admin", "master_admin"]:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    data = await request.json()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    user_type = data.get("user_type", "user").strip()
    full_name = data.get("full_name", "").strip()
    tokens = int(data.get("tokens", 100))
    
    if not email or not password:
        raise HTTPException(status_code=400, detail="Missing email or password")
        
    # Rule validation: Admin cannot create an admin/master_admin
    if actor.user_type == "admin" and user_type in ["admin", "master_admin"]:
        raise HTTPException(status_code=403, detail="Admins cannot create admin accounts")
        
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")
        
    hashed_pw = ph.hash(password)
    new_user = User(
        email=email,
        password=hashed_pw,
        user_type=user_type,
        full_name=full_name or email.split("@")[0].capitalize(),
        tokens=tokens
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"success": True, "user_id": new_user.id}

@app.put("/api/admin/users/{target_id}")
async def admin_update_user(target_id: int, request: Request, db: Session = Depends(get_db)):
    """Admin-only updates of roles, tokens, and names."""
    user_id = get_user_id(request)
    actor = db.query(User).filter(User.id == user_id).first()
    if not actor or actor.user_type not in ["admin", "master_admin"]:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    target = db.query(User).filter(User.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
        
    data = await request.json()
    new_role = data.get("user_type")
    new_full_name = data.get("full_name")
    new_tokens = data.get("tokens")
    
    # Check role update permission
    if new_role and new_role != target.user_type:
        if not verify_admin_action(actor, target, "update_role", new_role):
            raise HTTPException(status_code=403, detail="Permission denied to change role")
        target.user_type = new_role
        
    # Token assignment & profile updates
    if new_tokens is not None:
        if actor.user_type == "admin" and target.user_type in ["admin", "master_admin"]:
             raise HTTPException(status_code=403, detail="Cannot modify other admin tokens")
        target.tokens = int(new_tokens)
        
    if new_full_name is not None:
        if actor.user_type == "admin" and target.user_type in ["admin", "master_admin"]:
             raise HTTPException(status_code=403, detail="Cannot modify other admin profile")
        target.full_name = new_full_name
        
    db.commit()
    return {"success": True}

@app.post("/api/admin/users/{target_id}/reset-password")
async def admin_reset_password(target_id: int, request: Request, db: Session = Depends(get_db)):
    """Reset user password, respecting security boundaries."""
    user_id = get_user_id(request)
    actor = db.query(User).filter(User.id == user_id).first()
    if not actor or actor.user_type not in ["admin", "master_admin"]:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    target = db.query(User).filter(User.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
        
    data = await request.json()
    new_password = data.get("password")
    if not new_password or len(new_password.strip()) < 5:
        raise HTTPException(status_code=400, detail="Password too short")
        
    if not verify_admin_action(actor, target, "reset_password"):
        raise HTTPException(status_code=403, detail="Permission denied to reset password")
        
    target.password = ph.hash(new_password.strip())
    db.commit()
    return {"success": True}

@app.delete("/api/admin/users/{target_id}")
async def admin_delete_user(target_id: int, request: Request, db: Session = Depends(get_db)):
    """Delete a user account, respecting admin boundaries."""
    user_id = get_user_id(request)
    actor = db.query(User).filter(User.id == user_id).first()
    if not actor or actor.user_type not in ["admin", "master_admin"]:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    target = db.query(User).filter(User.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
        
    if not verify_admin_action(actor, target, "delete"):
        raise HTTPException(status_code=403, detail="Permission denied to delete user")
        
    db.delete(target)
    db.commit()
    return {"success": True}

@app.get("/api/admin/bookings")
async def admin_get_bookings(request: Request, db: Session = Depends(get_db)):
    """Fetch all bookings for appointment and video call assignment control."""
    user_id = get_user_id(request)
    actor = db.query(User).filter(User.id == user_id).first()
    if not actor or actor.user_type not in ["admin", "master_admin"]:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    bookings = db.query(SpecialistBooking).order_by(desc(SpecialistBooking.created_at)).all()
    results = []
    for b in bookings:
        client = db.query(User).filter(User.id == b.user_id).first()
        spec = db.query(User).filter(User.id == b.specialist_id).first() if b.specialist_id else None
        results.append({
            "id": b.id,
            "user_id": b.user_id,
            "client_email": client.email if client else "Unknown",
            "client_name": client.full_name if client else "Unknown",
            "specialist_id": b.specialist_id,
            "specialist_name": spec.full_name if spec else "Unassigned",
            "session_type": b.session_type,
            "date": b.date,
            "time": b.time,
            "status": b.status,
            "reason": b.reason,
            "notes": b.notes
        })
    return results

@app.put("/api/admin/bookings/{booking_id}")
async def admin_update_booking(booking_id: int, request: Request, db: Session = Depends(get_db)):
    """Admin-only reassignment and adjustment of bookings (video call control)."""
    user_id = get_user_id(request)
    actor = db.query(User).filter(User.id == user_id).first()
    if not actor or actor.user_type not in ["admin", "master_admin"]:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    booking = db.query(SpecialistBooking).filter(SpecialistBooking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
        
    data = await request.json()
    new_specialist_id = data.get("specialist_id")
    new_status = data.get("status")
    new_date = data.get("date")
    new_time = data.get("time")
    
    if new_specialist_id is not None:
        if new_specialist_id == 0 or new_specialist_id is None:
            booking.specialist_id = None
            booking.status = "pending"
        else:
            spec = db.query(User).filter(User.id == new_specialist_id, User.user_type == "specialist").first()
            if not spec:
                raise HTTPException(status_code=400, detail="Invalid specialist ID")
            booking.specialist_id = new_specialist_id
            booking.status = "assigned"
            
    if new_status:
        booking.status = new_status
    if new_date:
        booking.date = new_date
    if new_time:
        booking.time = new_time
        
    db.commit()
    return {"success": True}

@app.delete("/api/admin/bookings/{booking_id}")
async def admin_delete_booking(booking_id: int, request: Request, db: Session = Depends(get_db)):
    """Admin-only deletion of a booking."""
    user_id = get_user_id(request)
    actor = db.query(User).filter(User.id == user_id).first()
    if not actor or actor.user_type not in ["admin", "master_admin"]:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    booking = db.query(SpecialistBooking).filter(SpecialistBooking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
        
    db.delete(booking)
    db.commit()
    return {"success": True}

@app.get("/api/admin/specialist-requests")
async def admin_get_specialist_requests(request: Request, db: Session = Depends(get_db)):
    """Retrieve all users with pending specialist verification requests."""
    user_id = get_user_id(request)
    actor = db.query(User).filter(User.id == user_id).first()
    if not actor or actor.user_type not in ["admin", "master_admin"]:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    requests = db.query(User).filter(User.specialist_status == "pending").all()
    return [{
        "id": u.id,
        "email": u.email,
        "full_name": u.full_name or u.email.split("@")[0].capitalize(),
        "specialist_status": u.specialist_status,
        "specialist_details": u.specialist_details
    } for u in requests]

@app.post("/api/admin/specialist-requests/{target_id}/approve")
async def admin_approve_specialist_request(target_id: int, request: Request, db: Session = Depends(get_db)):
    """Approve a specialist request, upgrading user to specialist."""
    user_id = get_user_id(request)
    actor = db.query(User).filter(User.id == user_id).first()
    if not actor or actor.user_type not in ["admin", "master_admin"]:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    target = db.query(User).filter(User.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
        
    target.user_type = "specialist"
    target.specialist_status = "approved"
    db.commit()
    return {"success": True}

@app.post("/api/admin/specialist-requests/{target_id}/reject")
async def admin_reject_specialist_request(target_id: int, request: Request, db: Session = Depends(get_db)):
    """Reject a specialist request, resetting their specialist status."""
    user_id = get_user_id(request)
    actor = db.query(User).filter(User.id == user_id).first()
    if not actor or actor.user_type not in ["admin", "master_admin"]:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    target = db.query(User).filter(User.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
        
    target.specialist_status = "rejected"
    db.commit()
    return {"success": True}


# ==============================================================================
# 📹 WEBRTC VIDEO SIGNALING
# ==============================================================================

class VideoSignalingManager:
    def __init__(self):
        # Store active connections: booking_id -> {role: websocket}
        self.active_calls = {}

    async def connect(self, websocket: WebSocket, booking_id: int, role: str):
        await websocket.accept()
        if booking_id not in self.active_calls:
            self.active_calls[booking_id] = {}
        self.active_calls[booking_id][role] = websocket

    def disconnect(self, booking_id: int, role: str):
        if booking_id in self.active_calls:
            if role in self.active_calls[booking_id]:
                del self.active_calls[booking_id][role]
            if not self.active_calls[booking_id]:
                del self.active_calls[booking_id]

    async def send_to_partner(self, message: str, booking_id: int, sender_role: str):
        if booking_id in self.active_calls:
            for role, ws in self.active_calls[booking_id].items():
                if role != sender_role:
                    await ws.send_text(message)

video_manager = VideoSignalingManager()

@app.websocket("/ws/video/{booking_id}/{role}")
async def websocket_video_endpoint(websocket: WebSocket, booking_id: int, role: str):
    await video_manager.connect(websocket, booking_id, role)
    # Send current room status to the newly connected participant
    room_info = {
        "type": "room-status",
        "client_connected": "client" in video_manager.active_calls.get(booking_id, {}),
        "specialist_connected": "specialist" in video_manager.active_calls.get(booking_id, {})
    }
    await websocket.send_text(json.dumps(room_info))
    
    # Notify partner that a peer has joined
    await video_manager.send_to_partner(
        json.dumps({"type": "peer-joined", "role": role}),
        booking_id,
        role
    )
    try:
        while True:
            data = await websocket.receive_text()
            # Forward SDP offer/answer or ICE candidate
            await video_manager.send_to_partner(data, booking_id, role)
    except WebSocketDisconnect:
        video_manager.disconnect(booking_id, role)
        # Notify partner that peer has left
        await video_manager.send_to_partner(
            json.dumps({"type": "peer-left", "role": role}),
            booking_id,
            role
        )


# ==============================================================================
# 🚀 MAIN SERVER ENTRYPOINT
# ==============================================================================

# Mount the static frontend for all other client routes (fallback for local development)
if os.path.exists("frontend"):
    app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == '__main__':
    import uvicorn
    # Start the server on port 5000 (standard for local development URL)
    uvicorn.run(app, host="127.0.0.1", port=5000)
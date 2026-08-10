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

import os
import datetime
from typing import Optional
from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
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
    user_type = Column(String, nullable=False) # 'user' or 'specialist'
    tokens = Column(Integer, default=100)      # Welcome tokens bonus

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

# Create database tables
Base.metadata.create_all(bind=engine)

# Database Session Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==============================================================================
# 🚀 FASTAPI APP & INTERFACE CONFIGURATIONS
# ==============================================================================

app = FastAPI(title="MindMate AI — Full Stack Wellness Companion")

# Enable Cross-Origin Resource Sharing (CORS)
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins (local dev + any GitHub Pages subdomains)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Starlette Session Middleware (cookie-based login sessions fallback)
# Generates a random session secret key if not set in .env
SESSION_SECRET = os.getenv("SESSION_SECRET", os.urandom(24).hex())
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

# Mount frontend static directory (CSS, JS, manifest)
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

# Global vector store instance for RAG
vector_store = None


@app.on_event("startup")
async def startup_event():
    """Builds or loads the RAG vector index on startup."""
    global vector_store
    vector_store = bot.initialize_rag()


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
    return render(request, "specialist-dashboard.html")

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
            new_user = User(email=email, password=hashed_pw, user_type=user_type)
            db.add(new_user)
            db.commit()
            db.refresh(new_user)

            # Establish user session
            request.session['user_id'] = new_user.id
            request.session['email'] = new_user.email
            request.session['user_type'] = new_user.user_type

            redirect_url = "specialist-dashboard.html" if user_type == "specialist" else "choose-support.html"
            return {
                'success': True, 
                'message': 'Account created successfully!', 
                'redirect': redirect_url,
                'user_id': new_user.id,
                'email': new_user.email,
                'tokens': new_user.tokens
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

        redirect_url = "specialist-dashboard.html" if user.user_type == "specialist" else "choose-support.html"
        return {
            'success': True, 
            'message': 'Logged in successfully!', 
            'redirect': redirect_url,
            'user_id': user.id,
            'email': user.email,
            'tokens': user.tokens
        }
    except VerifyMismatchError:
        return JSONResponse({'success': False, 'message': 'Invalid credentials.'}, status_code=401)


@app.get("/api/logout", name="logout")
async def logout_handler(request: Request):
    """Clears user session cookies."""
    request.session.clear()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/api/session")
async def session_handler(request: Request):
    """Retrieves current user login state details."""
    if 'user_id' not in request.session:
        return {'logged_in': False}
        
    return {
        'logged_in': True,
        'user_id': request.session.get('user_id'),
        'email': request.session.get('email'),
        'user_type': request.session.get('user_type')
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
    assembles chat memory from DB, calls Mistral Large, logs interactions,
    and dynamically re-titles the thread on the first turn.
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
        # Step 3.1: Vector similarity search (fetch top 10 candidates)
        top_matches = vector_store.similarity_search(user_input, k=10)
        candidate_chunks = [match[0] for match in top_matches]
        
        # Step 3.2: Mistral Reranker (select top 3 from the 10 candidates)
        context_chunks = bot.rerank_documents(query=user_input, documents=candidate_chunks, k=3)
        
    # 4. Generate response using Mistral LLM (structured JSON mode)
    bot_result = bot.get_mistral_chat_response(user_input, chat_history, context_chunks)
    
    bot_reply = bot_result.get("response", "I'm here to listen. Tell me more.")
    emotion = bot_result.get("emotion", "sad")
    risk_level = bot_result.get("risk", "NORMAL")
    confidence = bot_result.get("confidence", "75%")
    
    # 5. Save interactions to database
    try:
        user_msg_db = ChatMessage(thread_id=thread_id, sender='user', message=user_input)
        bot_msg_db = ChatMessage(
            thread_id=thread_id, 
            sender='bot', 
            message=bot_reply, 
            emotion=emotion, 
            risk_level=risk_level
        )
        db.add(user_msg_db)
        db.add(bot_msg_db)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"⚠️ Error saving messages to database: {e}")
        
    # 6. Dynamically update thread title if this was the first user message
    title_updated = False
    new_title = thread.title
    total_messages = db.query(ChatMessage).filter(ChatMessage.thread_id == thread_id).count()
    
    if total_messages <= 2: # User message + Bot message = 2 messages
        new_title = bot.generate_thread_title(user_input)
        try:
            thread.title = new_title
            db.commit()
            title_updated = True
        except Exception as e:
            db.rollback()
            print(f"⚠️ Error updating thread title: {e}")
            
    return {
        'response': bot_reply,
        'emotion': emotion,
        'risk': risk_level,
        'confidence': confidence,
        'thread_id': thread_id,
        'thread_title': new_title if title_updated else None
    }


# ==============================================================================
# 🚀 MAIN SERVER ENTRYPOINT
# ==============================================================================

# Mount the static frontend for all other client routes (fallback)
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == '__main__':
    import uvicorn
    # Start the server on port 5000 (standard for local development URL)
    uvicorn.run(app, host="127.0.0.1", port=5000)
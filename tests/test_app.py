import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import app, Base, get_db, User, SpecialistBooking, SpecialistMessage

# Setup in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_mindmate.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="function", autouse=True)
def setup_database():
    # Create the database tables
    Base.metadata.create_all(bind=engine)
    
    # Clean tables
    db = TestingSessionLocal()
    db.query(SpecialistMessage).delete()
    db.query(SpecialistBooking).delete()
    db.query(User).delete()
    db.commit()

    # Seed users
    from app import ph
    test_users = [
        {"email": "user@mindmate.com", "password": "user123", "user_type": "user", "full_name": "Normal User"},
        {"email": "specialist@mindmate.com", "password": "specialist123", "user_type": "specialist", "full_name": "Dr. Sarah Johnson"},
        {"email": "admin@mindmate.com", "password": "admin123", "user_type": "admin", "full_name": "App Admin"},
        {"email": "masteradmin@mindmate.com", "password": "master123", "user_type": "master_admin", "full_name": "Master Admin"},
        {"email": "admin2@mindmate.com", "password": "admin123", "user_type": "admin", "full_name": "Admin Two"}
    ]
    for u in test_users:
        hashed = ph.hash(u["password"])
        db.add(User(email=u["email"], password=hashed, user_type=u["user_type"], full_name=u["full_name"], tokens=100))
    db.commit()
    db.close()
    
    yield
    
    # Tear down test db
    Base.metadata.drop_all(bind=engine)


def get_auth_client(email, password):
    client = TestClient(app)
    res = client.post("/api/auth", json={"email": email, "password": password, "action": "login"})
    assert res.status_code == 200
    return client


def test_health_endpoint():
    client = TestClient(app)
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"
    assert "timestamp" in res.json()


def test_seeded_users():
    client = TestClient(app)
    # Verify login user
    res = client.post("/api/auth", json={"email": "user@mindmate.com", "password": "user123", "action": "login"})
    assert res.status_code == 200
    assert res.json()["success"] is True
    assert res.json()["redirect"] == "choose-support.html"
    
    # Verify login specialist
    res = client.post("/api/auth", json={"email": "specialist@mindmate.com", "password": "specialist123", "action": "login"})
    assert res.status_code == 200
    assert res.json()["redirect"] == "specialist-console.html"


def test_admin_role_conversion_rules():
    # Log in as standard admin
    admin_client = get_auth_client("admin@mindmate.com", "admin123")
    
    # Get users list to find IDs
    res = admin_client.get("/api/admin/users")
    users = res.json()
    user_id = next(u["id"] for u in users if u["email"] == "user@mindmate.com")
    admin2_id = next(u["id"] for u in users if u["email"] == "admin2@mindmate.com")
    self_id = next(u["id"] for u in users if u["email"] == "admin@mindmate.com")
    master_id = next(u["id"] for u in users if u["email"] == "masteradmin@mindmate.com")

    # 1. Admin can convert User to Specialist and vice-versa
    res = admin_client.put(f"/api/admin/users/{user_id}", json={"user_type": "specialist"})
    assert res.status_code == 200
    
    res = admin_client.put(f"/api/admin/users/{user_id}", json={"user_type": "user"})
    assert res.status_code == 200

    # 2. No admin can promote user/specialist to admin
    res = admin_client.put(f"/api/admin/users/{user_id}", json={"user_type": "admin"})
    assert res.status_code == 403

    # 3. No admin can demote other admin or self
    res = admin_client.put(f"/api/admin/users/{admin2_id}", json={"user_type": "user"})
    assert res.status_code == 403
    
    res = admin_client.put(f"/api/admin/users/{self_id}", json={"user_type": "user"})
    assert res.status_code == 403

    # 4. Master admin is read-only to admins (cannot change role/tokens)
    res = admin_client.put(f"/api/admin/users/{master_id}", json={"user_type": "user"})
    assert res.status_code == 403


def test_admin_password_reset_rules():
    admin_client = get_auth_client("admin@mindmate.com", "admin123")
    
    res = admin_client.get("/api/admin/users")
    users = res.json()
    user_id = next(u["id"] for u in users if u["email"] == "user@mindmate.com")
    admin2_id = next(u["id"] for u in users if u["email"] == "admin2@mindmate.com")
    self_id = next(u["id"] for u in users if u["email"] == "admin@mindmate.com")
    master_id = next(u["id"] for u in users if u["email"] == "masteradmin@mindmate.com")

    # Admin can reset password of user, specialist, and self
    res = admin_client.post(f"/api/admin/users/{user_id}/reset-password", json={"password": "newuserpw"})
    assert res.status_code == 200
    
    res = admin_client.post(f"/api/admin/users/{self_id}/reset-password", json={"password": "newadminpw"})
    assert res.status_code == 200

    # Admin cannot reset other admins or master admin
    res = admin_client.post(f"/api/admin/users/{admin2_id}/reset-password", json={"password": "newadmin2pw"})
    assert res.status_code == 403
    
    res = admin_client.post(f"/api/admin/users/{master_id}/reset-password", json={"password": "newmasterpw"})
    assert res.status_code == 403


def test_master_admin_rules():
    master_client = get_auth_client("masteradmin@mindmate.com", "master123")
    
    res = master_client.get("/api/admin/users")
    users = res.json()
    user_id = next(u["id"] for u in users if u["email"] == "user@mindmate.com")
    admin_id = next(u["id"] for u in users if u["email"] == "admin@mindmate.com")
    self_id = next(u["id"] for u in users if u["email"] == "masteradmin@mindmate.com")

    # Master admin can promote user to admin
    res = master_client.put(f"/api/admin/users/{user_id}", json={"user_type": "admin"})
    assert res.status_code == 200
    
    # Master admin can demote admin to user
    res = master_client.put(f"/api/admin/users/{user_id}", json={"user_type": "user"})
    assert res.status_code == 200

    # Master admin can reset anyone's password (user, specialist, admin, self)
    res = master_client.post(f"/api/admin/users/{user_id}/reset-password", json={"password": "masterresetuser"})
    assert res.status_code == 200
    
    res = master_client.post(f"/api/admin/users/{admin_id}/reset-password", json={"password": "masterresetadmin"})
    assert res.status_code == 200
    
    res = master_client.post(f"/api/admin/users/{self_id}/reset-password", json={"password": "masterresetself"})
    assert res.status_code == 200


def test_self_demote_and_delete_protection():
    # 1. Test standard admin
    admin_client = get_auth_client("admin@mindmate.com", "admin123")
    res = admin_client.get("/api/admin/users")
    users = res.json()
    admin_self_id = next(u["id"] for u in users if u["email"] == "admin@mindmate.com")

    # Standard Admin tries to delete themselves
    res = admin_client.delete(f"/api/admin/users/{admin_self_id}")
    assert res.status_code == 403

    # Standard Admin tries to demote themselves
    res = admin_client.put(f"/api/admin/users/{admin_self_id}", json={"user_type": "user"})
    assert res.status_code == 403

    # 2. Test master admin
    master_client = get_auth_client("masteradmin@mindmate.com", "master123")
    res = master_client.get("/api/admin/users")
    users = res.json()
    master_self_id = next(u["id"] for u in users if u["email"] == "masteradmin@mindmate.com")

    # Master Admin tries to delete themselves
    res = master_client.delete(f"/api/admin/users/{master_self_id}")
    assert res.status_code == 403

    # Master Admin tries to demote themselves
    res = master_client.put(f"/api/admin/users/{master_self_id}", json={"user_type": "user"})
    assert res.status_code == 403


def test_booking_and_messaging():
    user_client = get_auth_client("user@mindmate.com", "user123")
    
    # Find specialist ID
    res = user_client.get("/api/specialists")
    specs = res.json()
    spec_id = specs[0]["id"]
    
    # Book a chat session (costs 50 tokens)
    # User started with 100 tokens
    res = user_client.post("/api/user/bookings", json={
        "specialist_id": spec_id,
        "session_type": "Text Chat",
        "date": "Tomorrow",
        "time": "10:00 AM",
        "reason": "Stress management"
    })
    assert res.status_code == 200
    booking_id = res.json()["booking_id"]
    assert res.json()["remaining_tokens"] == 50

    # Specialist logs in and views their bookings
    spec_client = get_auth_client("specialist@mindmate.com", "specialist123")
    res = spec_client.get("/api/specialist/bookings")
    assert res.status_code == 200
    bookings = res.json()
    assert len(bookings) > 0
    assert bookings[0]["id"] == booking_id
    
    # User sends a message
    res = user_client.post(f"/api/bookings/{booking_id}/messages", json={"message": "Hello Doctor"})
    assert res.status_code == 200
    
    # Specialist sends a message
    res = spec_client.post(f"/api/bookings/{booking_id}/messages", json={"message": "Hello Client, how can I help you?"})
    assert res.status_code == 200

    # Verify messages list
    res = user_client.get(f"/api/bookings/{booking_id}/messages")
    assert res.status_code == 200
    messages = res.json()
    assert len(messages) == 2
    assert messages[0]["message"] == "Hello Doctor"
    assert messages[1]["message"] == "Hello Client, how can I help you?"

    # Admin reassigns booking (assignment control)
    admin_client = get_auth_client("admin@mindmate.com", "admin123")
    # Let's change date and status
    res = admin_client.put(f"/api/admin/bookings/{booking_id}", json={
        "status": "completed",
        "date": "Next Monday"
    })
    assert res.status_code == 200
    
    # Verify changes
    res = admin_client.get("/api/admin/bookings")
    updated_bookings = res.json()
    target_booking = next(b for b in updated_bookings if b["id"] == booking_id)
    assert target_booking["status"] == "completed"
    assert target_booking["date"] == "Next Monday"

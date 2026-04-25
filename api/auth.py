import os
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from pathlib import Path

from api.database import (
    create_user, get_user_by_email, get_user_by_id, verify_user, user_exists,
    JWT_SECRET, create_session as db_create_session, get_sessions
)

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

for key in ["GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "RESEND_API_KEY"]:
    if not os.getenv(key):
        os.environ[key] = os.environ.get(key, "")

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Check if running locally (no DATABASE_URL = local dev mode)
def is_local_dev() -> bool:
    return not os.getenv("DATABASE_URL")

def validate_email(email: str) -> bool:
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_password(password: str) -> tuple[bool, str]:
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least one number"
    return True, ""

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hash: str) -> bool:
    """Verify password against hash"""
    try:
        return bcrypt.checkpw(password.encode(), hash.encode())
    except:
        return False

def create_token(user_id: int, email: str) -> str:
    """Create JWT token"""
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def decode_token(token: str) -> dict:
    """Decode JWT token"""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_current_user(request: Request) -> dict:
    """Get current authenticated user from token"""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = auth_header.replace("Bearer ", "")
    payload = decode_token(token)
    user = get_user_by_id(payload["user_id"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def send_verification_email(email: str, token: str, name: str) -> bool:
    """Send verification email using Resend"""
    resend_api_key = os.getenv("RESEND_API_KEY", "")
    
    # Dynamic verification URL based on environment
    base_url = os.getenv("RENDER_EXTERNAL_URL", "https://educhat.onrender.com")
    verification_url = f"{base_url}/api/auth/verify/{token}"
    print(f"=== VERIFICATION EMAIL ===")
    print(f"To: {email}")
    print(f"Verification URL: {verification_url}")
    print(f"=========================")
    
    if not resend_api_key:
        print(f"RESEND_API_KEY not set - Using debug link above")
        return False
    
    try:
        import resend
        
        response = resend.Emails.send({
            "api_key": resend_api_key,
            "from": "EduChat <onboarding@resend.dev>",
            "to": email,
            "subject": "Verify your EduChat account",
            "html": f"""
            <!DOCTYPE html>
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2>Welcome to EduChat, {name}!</h2>
                <p>Thank you for signing up. Please verify your email address to get started.</p>
                <a href="{verification_url}" style="background: #10b981; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block; margin: 20px 0;">Verify Email</a>
                <p>Or copy this link: {verification_url}</p>
                <p style="color: #666; font-size: 12px; margin-top: 30px;">If you didn't create an account, please ignore this email.</p>
            </body>
            </html>
            """
        })
        print(f"Resend response: {response}")
        return True
    except Exception as e:
        print(f"Email sending failed: {e}")
        return False

@router.post("/signup")
async def signup(
    email: str = Form(...),
    password: str = Form(...),
    name: str = Form(...)
):
    """Register a new user"""
    # Local dev mode - skip full auth
    if is_local_dev():
        if user_exists(email):
            return {"message": "User already exists (local mode)"}
        
        password_hash = hash_password(password)
        try:
            user_id = create_user(email, password_hash, name, None)
        except Exception as e:
            print(f"User creation failed: {e}")
            return JSONResponse({"error": "Failed to create user"}, status_code=500)
        
        return {
            "message": "Account created (local mode)",
            "user_id": user_id
        }
    
    # Validate email format
    if not validate_email(email):
        return JSONResponse({"error": "Invalid email format"}, status_code=400)
    
    # Check if user already exists
    if user_exists(email):
        return JSONResponse({"error": "User already exists"}, status_code=400)
    
    # Validate password strength
    valid, message = validate_password(password)
    if not valid:
        return JSONResponse({"error": message}, status_code=400)
    
    # Hash password
    password_hash = hash_password(password)
    
    # Create verification token
    verification_token = secrets.token_urlsafe(32)
    
    # Create user
    try:
        user_id = create_user(email, password_hash, name, verification_token)
    except Exception as e:
        print(f"User creation failed: {e}")
        return JSONResponse({"error": "Failed to create user"}, status_code=500)
    
    # Send verification email
    send_verification_email(email, verification_token, name)
    
    return {
        "message": "Account created! Please check your email to verify your account.",
        "user_id": user_id
    }

@router.post("/login")
async def login(
    email: str = Form(...),
    password: str = Form(...)
):
    """Login user"""
    # Get user
    user = get_user_by_email(email)
    if not user:
        return JSONResponse({"error": "Invalid email or password"}, status_code=401)
    
    # Verify password
    if not verify_password(password, user["password_hash"]):
        return JSONResponse({"error": "Invalid email or password"}, status_code=401)
    
    # Local dev mode - skip verification check
    if is_local_dev():
        token = create_token(user["id"], user["email"])
        session_id = db_create_session(user["id"], "New Chat")
        return {
            "token": token,
            "user": {
                "id": user["id"],
                "email": user["email"],
                "name": user["name"]
            },
            "session_id": session_id
        }
    
    # Check if verified (production)
    if not user["verified"]:
        return JSONResponse({"error": "Please verify your email first"}, status_code=401)
    
    # Create token
    token = create_token(user["id"], user["email"])
    
    # Create a default session
    session_id = db_create_session(user["id"], "New Chat")
    
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"]
        },
        "session_id": session_id
    }

@router.get("/verify/{token}")
async def verify_email(token: str):
    """Verify user email"""
    success = verify_user(token)
    if success:
        base_url = os.getenv("RENDER_EXTERNAL_URL", "https://educhat.onrender.com")
        return RedirectResponse(url=f"{base_url}?verified=true")
    return JSONResponse({"error": "Invalid or expired token"}, status_code=400)

@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Get current user info"""
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "verified": user["verified"]
    }

@router.post("/logout")
async def logout():
    """Logout user"""
    return {"message": "Logged out successfully"}
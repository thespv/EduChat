import os
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pathlib import Path

from api.database import (
    create_user, get_user_by_email, get_user_by_id, verify_user, user_exists,
    update_reset_token, get_user_by_reset_token, update_password,
    JWT_SECRET
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
    except Exception:
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
    base_url = os.getenv("RENDER_EXTERNAL_URL", "https://educhat.onrender.com")
    verification_url = f"{base_url}/api/auth/verify/{token}"
    
    if not resend_api_key:
        print(f"VERIFICATION LINK: {verification_url}")
        return False
    
    try:
        import resend
        resend.Emails.send({
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
    if not is_local_dev() and not verify_password(password, user["password_hash"]):
        return JSONResponse({"error": "Invalid email or password"}, status_code=401)
    
    # Local dev mode - skip verification check
    if is_local_dev():
        token = create_token(user["id"], user["email"])
        return {
            "token": token,
            "user": {
                "id": user["id"],
                "email": user["email"],
                "name": user["name"]
            }
        }
    
    # Check if verified (production)
    if not user["verified"]:
        return JSONResponse({"error": "Please verify your email first"}, status_code=401)
    
    # Create token
    token = create_token(user["id"], user["email"])
    
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"]
        }
    }

@router.get("/verify/{token}")
async def verify_email(token: str):
    """Verify user email"""
    success = verify_user(token)
    if success:
        base_url = os.getenv("RENDER_EXTERNAL_URL", "https://educhat.onrender.com")
        return RedirectResponse(url=f"{base_url}?verified=true")
    return JSONResponse({"error": "Invalid or expired token"}, status_code=400)

def send_reset_email(email: str, token: str, name: str) -> bool:
    """Send password reset email using Resend"""
    resend_api_key = os.getenv("RESEND_API_KEY", "")
    base_url = os.getenv("RENDER_EXTERNAL_URL", "https://educhat.onrender.com")
    reset_url = f"{base_url}/api/auth/reset/{token}"

    if not resend_api_key:
        print(f"RESET LINK: {reset_url}")
        return False

    try:
        import resend
        resend.Emails.send({
            "api_key": resend_api_key,
            "from": "EduChat <onboarding@resend.dev>",
            "to": email,
            "subject": "Reset your EduChat password",
            "html": f"""
            <!DOCTYPE html>
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2>Password Reset Request</h2>
                <p>Hi {name},</p>
                <p>We received a request to reset your EduChat password. Click the button below to set a new password.</p>
                <a href="{reset_url}" style="background: #6c63ff; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block; margin: 20px 0;">Reset Password</a>
                <p>Or copy this link: {reset_url}</p>
                <p style="color: #666; font-size: 12px;">This link expires in 1 hour.</p>
                <p style="color: #666; font-size: 12px; margin-top: 30px;">If you didn't request this, please ignore this email.</p>
            </body>
            </html>
            """
        })
        return True
    except Exception as e:
        print(f"Reset email sending failed: {e}")
        return False

@router.post("/forgot-password")
async def forgot_password(email: str = Form(...)):
    """Send password reset email (production only)"""
    if is_local_dev():
        return JSONResponse({"error": "Password reset is only available in production"}, status_code=400)

    user = get_user_by_email(email)
    if not user:
        return JSONResponse({"error": "If that email exists, a reset link has been sent"}, status_code=200)

    token = secrets.token_urlsafe(32)
    expiry = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    update_reset_token(email, token, expiry)
    send_reset_email(email, token, user["name"])

    return {"message": "If that email exists, a reset link has been sent"}

@router.get("/reset/{token}")
async def verify_reset_token(token: str):
    """Validate reset token and show reset page"""
    user = get_user_by_reset_token(token)
    if not user:
        return HTMLResponse("""
        <!DOCTYPE html>
        <html><body style="font-family:Arial;text-align:center;padding:40px;">
            <h2>Invalid or expired reset link</h2>
            <p>This password reset link is no longer valid.</p>
            <a href="https://educhat.onrender.com" style="color:#6c63ff;">Go to Login</a>
        </body></html>
        """, status_code=400)

    expiry = user["reset_token_expiry"]
    if expiry and datetime.fromisoformat(str(expiry)) < datetime.utcnow():
        return HTMLResponse("""
        <!DOCTYPE html>
        <html><body style="font-family:Arial;text-align:center;padding:40px;">
            <h2>Reset link expired</h2>
            <p>This password reset link has expired. Please request a new one.</p>
            <a href="https://educhat.onrender.com" style="color:#6c63ff;">Go to Login</a>
        </body></html>
        """, status_code=400)

    base_url = os.getenv("RENDER_EXTERNAL_URL", "https://educhat.onrender.com")
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Reset Password - EduChat</title>
        <style>
            *{{margin:0;padding:0;box-sizing:border-box;font-family:'Inter',Arial,sans-serif;}}
            body{{background:#0a0a18;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;}}
            .card{{background:rgba(255,255,255,0.03);backdrop-filter:blur(20px);border:1px solid rgba(108,99,255,0.2);border-radius:20px;padding:36px;max-width:420px;width:100%;box-shadow:0 20px 60px rgba(0,0,0,0.5);}}
            h2{{color:#e8e8f8;text-align:center;margin-bottom:6px;}}
            .sub{{color:#7a7a9d;text-align:center;margin-bottom:24px;font-size:0.88rem;}}
            .form-group{{margin-bottom:18px;}}
            label{{display:block;margin-bottom:7px;color:#9a9abd;font-weight:500;font-size:0.8rem;text-transform:uppercase;letter-spacing:0.6px;}}
            input{{width:100%;padding:13px 16px;background:rgba(255,255,255,0.05);border:1px solid rgba(108,99,255,0.25);border-radius:12px;font-size:0.95rem;color:#e8e8f8;outline:none;transition:all 0.2s;}}
            input:focus{{border-color:#6c63ff;background:rgba(108,99,255,0.08);box-shadow:0 0 0 3px rgba(108,99,255,0.2);}}
            .btn{{background:linear-gradient(135deg,#6c63ff,#5a52e0);color:white;border:none;padding:14px 24px;border-radius:12px;cursor:pointer;font-size:0.95rem;font-weight:600;width:100%;transition:all 0.25s;box-shadow:0 4px 20px rgba(108,99,255,0.4);}}
            .btn:hover{{transform:translateY(-2px);box-shadow:0 8px 30px rgba(108,99,255,0.55);}}
            .btn:disabled{{background:#2a2a45;color:#5a5a7a;cursor:not-allowed;transform:none;box-shadow:none;}}
            .error{{background:rgba(255,77,109,0.12);border:1px solid rgba(255,77,109,0.3);color:#ff6b8a;padding:10px 14px;border-radius:10px;margin-bottom:16px;text-align:center;display:none;}}
            .success{{background:rgba(0,212,170,0.1);border:1px solid rgba(0,212,170,0.3);color:#00d4aa;padding:10px 14px;border-radius:10px;margin-bottom:16px;text-align:center;display:none;}}
            .hint{{font-size:0.73rem;color:#5a5a7a;margin-top:5px;}}
            .footer{{text-align:center;margin-top:22px;color:#5a5a7a;font-size:0.88rem;}}
            .footer a{{color:#6c63ff;text-decoration:none;font-weight:600;}}
        </style>
    </head>
    <body>
        <div class="card">
            <h2>Reset Password</h2>
            <p class="sub">Enter your new password for EduChat</p>
            <div class="error" id="reset-error"></div>
            <div class="success" id="reset-success"></div>
            <form id="reset-form">
                <input type="hidden" id="reset-token" value="{token}">
                <div class="form-group">
                    <label for="new-password">New Password</label>
                    <input type="password" id="new-password" required placeholder="Enter new password" minlength="8">
                    <p class="hint">At least 8 characters, 1 uppercase, 1 lowercase, 1 number</p>
                </div>
                <div class="form-group">
                    <label for="confirm-password">Confirm Password</label>
                    <input type="password" id="confirm-password" required placeholder="Confirm new password">
                </div>
                <button type="submit" class="btn">Reset Password</button>
            </form>
            <div class="footer"><a href="{base_url}">Back to Login</a></div>
        </div>
        <script>
            document.getElementById('reset-form').addEventListener('submit', async (e) => {{
                e.preventDefault();
                const password = document.getElementById('new-password').value;
                const confirm = document.getElementById('confirm-password').value;
                const token = document.getElementById('reset-token').value;
                const errorDiv = document.getElementById('reset-error');
                const successDiv = document.getElementById('reset-success');
                const btn = e.target.querySelector('button');

                errorDiv.style.display = 'none';
                successDiv.style.display = 'none';

                if (password !== confirm) {{
                    errorDiv.textContent = 'Passwords do not match!';
                    errorDiv.style.display = 'block';
                    return;
                }}
                if (password.length < 8) {{
                    errorDiv.textContent = 'Password must be at least 8 characters';
                    errorDiv.style.display = 'block';
                    return;
                }}

                btn.disabled = true;
                btn.textContent = 'Resetting...';

                try {{
                    const formData = new FormData();
                    formData.append('token', token);
                    formData.append('password', password);

                    const response = await fetch('{base_url}/api/auth/reset-password', {{
                        method: 'POST',
                        body: formData
                    }});
                    const data = await response.json();

                    if (!response.ok) {{
                        errorDiv.textContent = data.error || 'Reset failed';
                        errorDiv.style.display = 'block';
                        return;
                    }}

                    successDiv.textContent = 'Password reset successfully! Redirecting to login...';
                    successDiv.style.display = 'block';
                    setTimeout(() => window.location.href = '{base_url}', 2000);
                }} catch (err) {{
                    errorDiv.textContent = 'Network error. Please try again.';
                    errorDiv.style.display = 'block';
                }} finally {{
                    btn.disabled = false;
                    btn.textContent = 'Reset Password';
                }}
            }});
        </script>
    </body>
    </html>
    """)

@router.post("/reset-password")
async def reset_password(token: str = Form(...), password: str = Form(...)):
    """Reset password using reset token"""
    user = get_user_by_reset_token(token)
    if not user:
        return JSONResponse({"error": "Invalid or expired reset token"}, status_code=400)

    expiry = user["reset_token_expiry"]
    if expiry and datetime.fromisoformat(str(expiry)) < datetime.utcnow():
        return JSONResponse({"error": "Reset token has expired"}, status_code=400)

    valid, message = validate_password(password)
    if not valid:
        return JSONResponse({"error": message}, status_code=400)

    password_hash = hash_password(password)
    update_password(user["id"], password_hash)

    return {"message": "Password reset successfully"}

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
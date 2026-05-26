import os
import sqlite3
import json
import secrets
from pathlib import Path
from datetime import datetime

# Database path for local SQLite
DB_PATH = Path("educhat_history.db")

# PostgreSQL connection (for Render/Production)
DATABASE_URL = os.getenv("DATABASE_URL", "")
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))
pg_conn = None

def get_pg_connection():
    global pg_conn
    if not DATABASE_URL:
        return None
    
    import psycopg2
    try:
        if pg_conn is not None:
            try:
                pg_conn.cursor().execute("SELECT 1")
                return pg_conn
            except:
                pg_conn = None
        
        # Render provides postgres:// urls, but psycopg2 prefers postgresql://
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
            
        pg_conn = psycopg2.connect(url)
        pg_conn.autocommit = True
        return pg_conn
    except Exception as e:
        print(f"PostgreSQL connection failed: {e}")
        return None

def init_db():
    """Initialize database - SQLite for local, PostgreSQL for production"""
    if DATABASE_URL:
        init_postgres()
    else:
        init_sqlite()

def init_sqlite():
    """Initialize SQLite database (local development)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            verified INTEGER DEFAULT 0,
            verification_token TEXT,
            reset_token TEXT,
            reset_token_expiry TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lecture_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            content TEXT NOT NULL,
            file_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()

    # Migration: add reset_token columns for existing databases
    try:
        conn2 = sqlite3.connect(DB_PATH)
        c2 = conn2.cursor()
        c2.execute("ALTER TABLE users ADD COLUMN reset_token TEXT")
        conn2.commit()
        conn2.close()
    except Exception:
        pass

    try:
        conn2 = sqlite3.connect(DB_PATH)
        c2 = conn2.cursor()
        c2.execute("ALTER TABLE users ADD COLUMN reset_token_expiry TIMESTAMP")
        conn2.commit()
        conn2.close()
    except Exception:
        pass

def init_postgres():
    """Initialize PostgreSQL tables"""
    conn = get_pg_connection()
    if not conn:
        print("Warning: PostgreSQL not connected, falling back to SQLite")
        init_sqlite()
        return
    
    cursor = conn.cursor()
    
    # Check for migration
    try:
        cursor.execute("SELECT tablename FROM pg_tables WHERE tablename = 'schema_migrations'")
        if not cursor.fetchone():
            cursor.execute("""
                CREATE TABLE schema_migrations (
                    id SERIAL PRIMARY KEY,
                    migration_name TEXT NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("INSERT INTO schema_migrations (migration_name) VALUES ('initial_schema')")
            conn.commit()
    except Exception as e:
        print(f"Migration check error: {e}")
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            verified BOOLEAN DEFAULT FALSE,
            verification_token TEXT,
            reset_token TEXT,
            reset_token_expiry TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id SERIAL PRIMARY KEY,
            session_id INTEGER NOT NULL,
            "role" TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lecture_notes (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            content TEXT NOT NULL,
            file_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    
    conn.commit()

    # Migration: add reset_token columns for existing databases
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token TEXT")
        conn.commit()
    except Exception as e:
        print(f"reset_token column migration note: {e}")

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_expiry TIMESTAMP")
        conn.commit()
    except Exception as e:
        print(f"reset_token_expiry column migration note: {e}")

    cursor.close()

# Operation helpers to reduce duplication
def execute_query(query, params=(), fetchone=False, fetchall=False, commit=True):
    if DATABASE_URL:
        conn = get_pg_connection()
        if not conn: return None
        # Convert ? to %s for PostgreSQL
        query = query.replace("?", "%s")
    else:
        conn = sqlite3.connect(DB_PATH)
    
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        
        result = None
        if fetchone:
            result = cursor.fetchone()
        elif fetchall:
            result = cursor.fetchall()
        elif "RETURNING id" in query or "returning id" in query.lower():
            result = cursor.fetchone()
        elif not DATABASE_URL and ("INSERT" in query.upper() or "REPLACE" in query.upper()):
            result = [cursor.lastrowid] # Wrap in list to match pg fetchone pattern
            
        if commit:
            conn.commit()
        
        if DATABASE_URL:
            cursor.close()
        else:
            conn.close()
            
        return result
    except Exception as e:
        print(f"Database query failed: {e}")
        if not DATABASE_URL: conn.close()
        return None

def save_lecture_note(user_id: int, name: str, content: str, file_type: str) -> int:
    query = "INSERT INTO lecture_notes (user_id, name, content, file_type) VALUES (?, ?, ?, ?) RETURNING id" if DATABASE_URL else "INSERT INTO lecture_notes (user_id, name, content, file_type) VALUES (?, ?, ?, ?)"
    res = execute_query(query, (user_id, name, content, file_type))
    return res[0] if res else None

def get_lecture_notes(user_id: int) -> list:
    res = execute_query("SELECT id, name, content, file_type, created_at FROM lecture_notes WHERE user_id = ? ORDER BY created_at DESC", (user_id,), fetchall=True)
    if not res: return []
    return [{"id": r[0], "name": r[1], "content": r[2], "file_type": r[3], "created_at": str(r[4])} for r in res]

def get_lecture_note_by_id(note_id: int) -> dict:
    res = execute_query("SELECT id, name, content, file_type, created_at FROM lecture_notes WHERE id = ?", (note_id,), fetchone=True)
    if not res: return None
    return {"id": res[0], "name": res[1], "content": res[2], "file_type": res[3], "created_at": str(res[4])}

def delete_lecture_note(note_id: int):
    execute_query("DELETE FROM lecture_notes WHERE id = ?", (note_id,))

def create_user(email: str, password_hash: str, name: str, verification_token: str = None) -> int:
    query = "INSERT INTO users (email, password_hash, name, verification_token) VALUES (?, ?, ?, ?) RETURNING id" if DATABASE_URL else "INSERT INTO users (email, password_hash, name, verification_token) VALUES (?, ?, ?, ?)"
    res = execute_query(query, (email, password_hash, name, verification_token))
    return res[0] if res else None

def get_user_by_email(email: str) -> dict:
    res = execute_query("SELECT id, email, password_hash, name, verified, verification_token, created_at FROM users WHERE email = ?", (email,), fetchone=True)
    if not res: return None
    return {"id": res[0], "email": res[1], "password_hash": res[2], "name": res[3], "verified": bool(res[4]), "verification_token": res[5], "created_at": str(res[6])}

def get_user_by_id(user_id: int) -> dict:
    res = execute_query("SELECT id, email, name, verified, created_at FROM users WHERE id = ?", (user_id,), fetchone=True)
    if not res: return None
    return {"id": res[0], "email": res[1], "name": res[2], "verified": bool(res[3]), "created_at": str(res[4])}

def verify_user(token: str) -> bool:
    # Postgre uses TRUE, SQLite uses 1
    val = "TRUE" if DATABASE_URL else 1
    query = f"UPDATE users SET verified = {val}, verification_token = NULL WHERE verification_token = ?"
    # execute_query returns None for update, so we need rowcount which is not in our helper yet.
    # For now, keep it simple and just do it manually or adapt helper.
    # Actually, rowcount is needed. Let's stick to the current specific implementations for verify to be sure.
    if DATABASE_URL:
        conn = get_pg_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET verified = TRUE, verification_token = NULL WHERE verification_token = %s", (token,))
        updated = cursor.rowcount > 0
        cursor.close()
    else:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET verified = 1, verification_token = NULL WHERE verification_token = ?", (token,))
        conn.commit()
        updated = cursor.rowcount > 0
        conn.close()
    return updated

def user_exists(email: str) -> bool:
    return get_user_by_email(email) is not None

def update_reset_token(email: str, token: str, expiry: str) -> bool:
    res = execute_query("UPDATE users SET reset_token = ?, reset_token_expiry = ? WHERE email = ?", (token, expiry, email))
    return True

def get_user_by_reset_token(token: str) -> dict:
    res = execute_query("SELECT id, email, name, reset_token_expiry FROM users WHERE reset_token = ?", (token,), fetchone=True)
    if not res: return None
    return {"id": res[0], "email": res[1], "name": res[2], "reset_token_expiry": res[3]}

def update_password(user_id: int, password_hash: str) -> bool:
    execute_query("UPDATE users SET password_hash = ?, reset_token = NULL, reset_token_expiry = NULL WHERE id = ?", (password_hash, user_id))
    return True

def create_session(user_id: int, title: str = "New Chat") -> int:
    query = "INSERT INTO chat_sessions (user_id, title) VALUES (?, ?) RETURNING id" if DATABASE_URL else "INSERT INTO chat_sessions (user_id, title) VALUES (?, ?)"
    res = execute_query(query, (user_id, title))
    return res[0] if res else None

def get_sessions(user_id: int) -> list:
    res = execute_query("SELECT id, title, created_at, updated_at FROM chat_sessions WHERE user_id = ? ORDER BY updated_at DESC", (user_id,), fetchall=True)
    if not res: return []
    return [{"id": r[0], "title": r[1], "created_at": str(r[2]), "updated_at": str(r[3])} for r in res]

def get_session(session_id: int, user_id: int) -> dict:
    session = execute_query("SELECT id, user_id, title, created_at FROM chat_sessions WHERE id = ? AND user_id = ?", (session_id, user_id), fetchone=True)
    if not session: return None
    
    msgs = execute_query("SELECT role, content, created_at FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC", (session_id,), fetchall=True)
    messages = [{"role": m[0], "content": m[1], "created_at": str(m[2])} for m in msgs] if msgs else []
    
    return {"id": session[0], "user_id": session[1], "title": session[2], "created_at": str(session[3]), "messages": messages}

def delete_session(session_id: int, user_id: int):
    execute_query("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
    execute_query("DELETE FROM chat_sessions WHERE id = ? AND user_id = ?", (session_id, user_id))

def update_session_title(session_id: int, user_id: int, title: str):
    execute_query("UPDATE chat_sessions SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?", (title, session_id, user_id))

def add_message(session_id: int, role: str, content: str):
    execute_query("INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)", (session_id, role, content))
    execute_query("UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (session_id,))

if __name__ == "__main__":
    init_db()
    print("Database initialized!")
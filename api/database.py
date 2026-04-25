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
    
    if pg_conn is None:
        import psycopg2
        try:
            pg_conn = psycopg2.connect(DATABASE_URL)
        except Exception as e:
            print(f"PostgreSQL connection failed: {e}")
            return None
    return pg_conn

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
    
    # Users table for authentication
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            verified INTEGER DEFAULT 0,
            verification_token TEXT,
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

def init_postgres():
    """Initialize PostgreSQL tables"""
    conn = get_pg_connection()
    if not conn:
        print("Warning: PostgreSQL not connected, falling back to SQLite")
        init_sqlite()
        return
    
    cursor = conn.cursor()
    
    # Check if migration already done
    try:
        cursor.execute("SELECT tablename FROM pg_tables WHERE tablename = 'schema_migrations'")
        migration_done = cursor.fetchone()
        
        if not migration_done:
            # Check if old schema exists and needs migration
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'chat_sessions' AND column_name = 'id'")
            old_schema = cursor.fetchone()
            
            if old_schema:
                # Old schema exists, drop and recreate
                print("Migrating database schema...")
                cursor.execute("DROP TABLE IF EXISTS chat_messages CASCADE")
                cursor.execute("DROP TABLE IF EXISTS chat_sessions CASCADE")
                cursor.execute("DROP TABLE IF EXISTS lecture_notes CASCADE")
                cursor.execute("DROP TABLE IF EXISTS users CASCADE")
                conn.commit()
            
            # Create migration tracking table
            cursor.execute("""
                CREATE TABLE schema_migrations (
                    id SERIAL PRIMARY KEY,
                    migration_name TEXT NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("INSERT INTO schema_migrations (migration_name) VALUES ('initial_schema')")
            conn.commit()
            print("Database migration completed")
    except Exception as e:
        print(f"Migration check error (may be first run): {e}")
    
    # Users table for authentication
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            verified BOOLEAN DEFAULT FALSE,
            verification_token TEXT,
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
    cursor.close()

# ============================================================
# User Authentication Functions
# ============================================================

def create_user(email: str, password_hash: str, name: str, verification_token: str = None) -> int:
    if DATABASE_URL:
        return get_sessions_pg(user)
    return get_sessions_sqlite(user)

def get_sessions_sqlite(user: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, created_at, updated_at 
        FROM chat_sessions 
        WHERE user = ? 
        ORDER BY updated_at DESC
    """, (user,))
    
    sessions = []
    for row in cursor.fetchall():
        sessions.append({"id": row[0], "title": row[1], "created_at": row[2], "updated_at": row[3]})
    conn.close()
    return sessions

def get_sessions_pg(user: str) -> list:
    conn = get_pg_connection()
    if not conn:
        return get_sessions_sqlite(user)
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, created_at, updated_at 
        FROM chat_sessions 
        WHERE "user" = %s 
        ORDER BY updated_at DESC
    """, (user,))
    
    sessions = []
    for row in cursor.fetchall():
        sessions.append({"id": row[0], "title": row[1], "created_at": str(row[2]), "updated_at": str(row[3])})
    cursor.close()
    return sessions

def get_session(session_id: int) -> dict:
    if DATABASE_URL:
        return get_session_pg(session_id)
    return get_session_sqlite(session_id)

def get_session_sqlite(session_id: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, user, title, created_at FROM chat_sessions WHERE id = ?", (session_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    
    cursor.execute("SELECT role, content, created_at FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC", (session_id,))
    
    messages = [{"role": m[0], "content": m[1], "created_at": m[2]} for m in cursor.fetchall()]
    conn.close()
    return {"id": row[0], "user": row[1], "title": row[2], "created_at": row[3], "messages": messages}

def get_session_pg(session_id: int) -> dict:
    conn = get_pg_connection()
    if not conn:
        return get_session_sqlite(session_id)
    
    cursor = conn.cursor()
    cursor.execute("SELECT id, \"user\", title, created_at FROM chat_sessions WHERE id = %s", (session_id,))
    row = cursor.fetchone()
    if not row:
        cursor.close()
        return None
    
    cursor.execute("SELECT \"role\", content, created_at FROM chat_messages WHERE session_id = %s ORDER BY created_at ASC", (session_id,))
    messages = [{"role": m[0], "content": m[1], "created_at": str(m[2])} for m in cursor.fetchall()]
    cursor.close()
    return {"id": row[0], "user": row[1], "title": row[2], "created_at": str(row[3]), "messages": messages}

def add_message(session_id: int, role: str, content: str):
    if DATABASE_URL:
        add_message_pg(session_id, role, content)
    else:
        add_message_sqlite(session_id, role, content)

def add_message_sqlite(session_id: int, role: str, content: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)", (session_id, role, content))
    cursor.execute("UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()

def add_message_pg(session_id: int, role: str, content: str):
    conn = get_pg_connection()
    if not conn:
        add_message_sqlite(session_id, role, content)
        return
    
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_messages (session_id, \"role\", content) VALUES (%s, %s, %s)", (session_id, role, content))
    cursor.execute("UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = %s", (session_id,))
    conn.commit()
    cursor.close()

def update_session_title(session_id: int, title: str):
    if DATABASE_URL:
        update_session_title_pg(session_id, title)
    else:
        update_session_title_sqlite(session_id, title)

def update_session_title_sqlite(session_id: int, title: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE chat_sessions SET title = ? WHERE id = ?", (title, session_id))
    conn.commit()
    conn.close()

def update_session_title_pg(session_id: int, title: str):
    conn = get_pg_connection()
    if not conn:
        update_session_title_sqlite(session_id, title)
        return
    
    cursor = conn.cursor()
    cursor.execute("UPDATE chat_sessions SET title = %s WHERE id = %s", (title, session_id))
    conn.commit()
    cursor.close()

def delete_session(session_id: int):
    if DATABASE_URL:
        delete_session_pg(session_id)
    else:
        delete_session_sqlite(session_id)

def delete_session_sqlite(session_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()

def delete_session_pg(session_id: int):
    conn = get_pg_connection()
    if not conn:
        delete_session_sqlite(session_id)
        return
    
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_messages WHERE session_id = %s", (session_id,))
    cursor.execute("DELETE FROM chat_sessions WHERE id = %s", (session_id,))
    conn.commit()
    cursor.close()

def save_lecture_note(user: str, name: str, content: str, file_type: str) -> int:
    if DATABASE_URL:
        return save_lecture_note_pg(user, name, content, file_type)
    return save_lecture_note_sqlite(user, name, content, file_type)

def save_lecture_note_sqlite(user: str, name: str, content: str, file_type: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO lecture_notes (user, name, content, file_type) VALUES (?, ?, ?, ?)", (user, name, content, file_type))
    note_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return note_id

def save_lecture_note_pg(user: str, name: str, content: str, file_type: str) -> int:
    conn = get_pg_connection()
    if not conn:
        return save_lecture_note_sqlite(user, name, content, file_type)
    
    cursor = conn.cursor()
    cursor.execute("INSERT INTO lecture_notes (\"user\", name, content, file_type) VALUES (%s, %s, %s, %s) RETURNING id", (user, name, content, file_type))
    note_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    return note_id

def get_lecture_notes(user: str) -> list:
    if DATABASE_URL:
        return get_lecture_notes_pg(user)
    return get_lecture_notes_sqlite(user)

def get_lecture_note_by_id(note_id: int) -> dict:
    if DATABASE_URL:
        return get_lecture_note_by_id_pg(note_id)
    return get_lecture_note_by_id_sqlite(note_id)

def get_lecture_note_by_id_sqlite(note_id: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, content, file_type, created_at FROM lecture_notes WHERE id = ?", (note_id,))
    r = cursor.fetchone()
    conn.close()
    if r:
        return {"id": r[0], "name": r[1], "content": r[2], "file_type": r[3], "created_at": r[4]}
    return None

def get_lecture_note_by_id_pg(note_id: int) -> dict:
    conn = get_pg_connection()
    if not conn:
        return get_lecture_note_by_id_sqlite(note_id)
    
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, content, file_type, created_at FROM lecture_notes WHERE id = %s", (note_id,))
    r = cursor.fetchone()
    cursor.close()
    if r:
        return {"id": r[0], "name": r[1], "content": r[2], "file_type": r[3], "created_at": str(r[4])}
    return None

def get_lecture_notes_sqlite(user: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, content, file_type, created_at FROM lecture_notes WHERE user = ? ORDER BY created_at DESC", (user,))
    notes = [{"id": r[0], "name": r[1], "content": r[2], "file_type": r[3], "created_at": r[4]} for r in cursor.fetchall()]
    conn.close()
    return notes

def get_lecture_notes_pg(user: str) -> list:
    conn = get_pg_connection()
    if not conn:
        return get_lecture_notes_sqlite(user)
    
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, content, file_type, created_at FROM lecture_notes WHERE \"user\" = %s ORDER BY created_at DESC", (user,))
    notes = [{"id": r[0], "name": r[1], "content": r[2], "file_type": r[3], "created_at": str(r[4])} for r in cursor.fetchall()]
    cursor.close()
    return notes

def delete_lecture_note(note_id: int):
    if DATABASE_URL:
        delete_lecture_note_pg(note_id)
    else:
        delete_lecture_note_sqlite(note_id)

def delete_lecture_note_sqlite(note_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM lecture_notes WHERE id = ?", (note_id,))
    conn.commit()
    conn.close()

def delete_lecture_note_pg(note_id: int):
    conn = get_pg_connection()
    if not conn:
        delete_lecture_note_sqlite(note_id)
        return
    
    cursor = conn.cursor()
    cursor.execute("DELETE FROM lecture_notes WHERE id = %s", (note_id,))
    conn.commit()
    cursor.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized!")

# ============================================================
# User Authentication Functions
# ============================================================

def create_user(email: str, password_hash: str, name: str, verification_token: str = None) -> int:
    """Create a new user"""
    if DATABASE_URL:
        return create_user_pg(email, password_hash, name, verification_token)
    return create_user_sqlite(email, password_hash, name, verification_token)

def create_user_sqlite(email: str, password_hash: str, name: str, verification_token: str = None) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (email, password_hash, name, verification_token) VALUES (?, ?, ?, ?)",
        (email, password_hash, name, verification_token)
    )
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    return user_id

def create_user_pg(email: str, password_hash: str, name: str, verification_token: str = None) -> int:
    conn = get_pg_connection()
    if not conn:
        return create_user_sqlite(email, password_hash, name, verification_token)
    
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (email, password_hash, name, verification_token) VALUES (%s, %s, %s, %s) RETURNING id",
        (email, password_hash, name, verification_token)
    )
    user_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    return user_id

def get_user_by_email(email: str) -> dict:
    """Get user by email"""
    if DATABASE_URL:
        return get_user_by_email_pg(email)
    return get_user_by_email_sqlite(email)

def get_user_by_email_sqlite(email: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, password_hash, name, verified, verification_token, created_at FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "email": row[1], "password_hash": row[2], "name": row[3], "verified": bool(row[4]), "verification_token": row[5], "created_at": row[6]}

def get_user_by_email_pg(email: str) -> dict:
    conn = get_pg_connection()
    if not conn:
        return get_user_by_email_sqlite(email)
    
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, password_hash, name, verified, verification_token, created_at FROM users WHERE email = %s", (email,))
    row = cursor.fetchone()
    cursor.close()
    if not row:
        return None
    return {"id": row[0], "email": row[1], "password_hash": row[2], "name": row[3], "verified": row[4], "verification_token": row[5], "created_at": str(row[6])}

def get_user_by_id(user_id: int) -> dict:
    """Get user by ID"""
    if DATABASE_URL:
        return get_user_by_id_pg(user_id)
    return get_user_by_id_sqlite(user_id)

def get_user_by_id_sqlite(user_id: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, name, verified, created_at FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "email": row[1], "name": row[2], "verified": bool(row[3]), "created_at": row[4]}

def get_user_by_id_pg(user_id: int) -> dict:
    conn = get_pg_connection()
    if not conn:
        return get_user_by_id_sqlite(user_id)
    
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, name, verified, created_at FROM users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    if not row:
        return None
    return {"id": row[0], "email": row[1], "name": row[2], "verified": row[3], "created_at": str(row[4])}

def verify_user(token: str) -> bool:
    """Verify user email with token"""
    if DATABASE_URL:
        return verify_user_pg(token)
    return verify_user_sqlite(token)

def verify_user_sqlite(token: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET verified = 1, verification_token = NULL WHERE verification_token = ?", (token,))
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated

def verify_user_pg(token: str) -> bool:
    conn = get_pg_connection()
    if not conn:
        return verify_user_sqlite(token)
    
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET verified = TRUE, verification_token = NULL WHERE verification_token = %s", (token,))
    conn.commit()
    updated = cursor.rowcount > 0
    cursor.close()
    return updated

def user_exists(email: str) -> bool:
    """Check if user exists"""
    user = get_user_by_email(email)
    return user is not None

# ============================================================
# Sessions - Updated for user_id based
# ============================================================

def create_session(user_id: int, title: str = "New Chat") -> int:
    """Create a new chat session"""
    if DATABASE_URL:
        return create_session_pg(user_id, title)
    return create_session_sqlite(user_id, title)

def create_session_sqlite(user_id: int, title: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_sessions (user_id, title) VALUES (?, ?)", (user_id, title))
    conn.commit()
    session_id = cursor.lastrowid
    conn.close()
    return session_id

def create_session_pg(user_id: int, title: str) -> int:
    conn = get_pg_connection()
    if not conn:
        return create_session_sqlite(user_id, title)
    
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_sessions (user_id, title) VALUES (%s, %s) RETURNING id", (user_id, title))
    session_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    return session_id

def get_sessions(user_id: int) -> list:
    """Get all sessions for a user"""
    if DATABASE_URL:
        return get_sessions_pg(user_id)
    return get_sessions_sqlite(user_id)

def get_sessions_sqlite(user_id: int) -> list:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, created_at, updated_at FROM chat_sessions WHERE user_id = ? ORDER BY updated_at DESC", (user_id,))
    sessions = [{"id": row[0], "title": row[1], "created_at": row[2], "updated_at": row[3]} for row in cursor.fetchall()]
    conn.close()
    return sessions

def get_sessions_pg(user_id: int) -> list:
    conn = get_pg_connection()
    if not conn:
        return get_sessions_sqlite(user_id)
    
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, created_at, updated_at FROM chat_sessions WHERE user_id = %s ORDER BY updated_at DESC", (user_id,))
    sessions = [{"id": row[0], "title": row[1], "created_at": str(row[2]), "updated_at": str(row[3])} for row in cursor.fetchall()]
    cursor.close()
    return sessions

def get_session(session_id: int, user_id: int) -> dict:
    """Get a specific session"""
    if DATABASE_URL:
        return get_session_pg(session_id, user_id)
    return get_session_sqlite(session_id, user_id)

def get_session_sqlite(session_id: int, user_id: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, title, created_at FROM chat_sessions WHERE id = ? AND user_id = ?", (session_id, user_id))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    
    cursor.execute("SELECT role, content, created_at FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC", (session_id,))
    messages = [{"role": m[0], "content": m[1], "created_at": m[2]} for m in cursor.fetchall()]
    conn.close()
    return {"id": row[0], "user_id": row[1], "title": row[2], "created_at": row[3], "messages": messages}

def get_session_pg(session_id: int, user_id: int) -> dict:
    conn = get_pg_connection()
    if not conn:
        return get_session_sqlite(session_id, user_id)
    
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, title, created_at FROM chat_sessions WHERE id = %s AND user_id = %s", (session_id, user_id))
    row = cursor.fetchone()
    if not row:
        cursor.close()
        return None
    
    cursor.execute("SELECT role, content, created_at FROM chat_messages WHERE session_id = %s ORDER BY created_at ASC", (session_id,))
    messages = [{"role": m[0], "content": m[1], "created_at": str(m[2])} for m in cursor.fetchall()]
    cursor.close()
    return {"id": row[0], "user_id": row[1], "title": row[2], "created_at": str(row[3]), "messages": messages}

def get_notes(user_id: int):
    """Get lecture notes for a user"""
    if DATABASE_URL:
        return get_notes_pg(user_id)
    return get_notes_sqlite(user_id)

def get_notes_sqlite(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, file_type, created_at FROM lecture_notes WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    notes = [{"id": row[0], "name": row[1], "file_type": row[2], "created_at": row[3]} for row in cursor.fetchall()]
    conn.close()
    return notes

def get_notes_pg(user_id: int):
    conn = get_pg_connection()
    if not conn:
        return get_notes_sqlite(user_id)
    
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, file_type, created_at FROM lecture_notes WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
    notes = [{"id": row[0], "name": row[1], "file_type": row[2], "created_at": str(row[3])} for row in cursor.fetchall()]
    cursor.close()
    return notes

def delete_session(session_id: int, user_id: int):
    """Delete a session"""
    if DATABASE_URL:
        delete_session_pg(session_id, user_id)
    else:
        delete_session_sqlite(session_id, user_id)

def delete_session_sqlite(session_id: int, user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM chat_sessions WHERE id = ? AND user_id = ?", (session_id, user_id))
    conn.commit()
    conn.close()

def delete_session_pg(session_id: int, user_id: int):
    conn = get_pg_connection()
    if not conn:
        delete_session_sqlite(session_id, user_id)
        return
    
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_messages WHERE session_id = %s", (session_id,))
    cursor.execute("DELETE FROM chat_sessions WHERE id = %s AND user_id = %s", (session_id, user_id))
    conn.commit()
    cursor.close()

def update_session_title(session_id: int, user_id: int, title: str):
    """Update session title"""
    if DATABASE_URL:
        update_session_title_pg(session_id, user_id, title)
    else:
        update_session_title_sqlite(session_id, user_id, title)

def update_session_title_sqlite(session_id: int, user_id: int, title: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE chat_sessions SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?", (title, session_id, user_id))
    conn.commit()
    conn.close()

def update_session_title_pg(session_id: int, user_id: int, title: str):
    conn = get_pg_connection()
    if not conn:
        update_session_title_sqlite(session_id, user_id, title)
        return
    
    cursor = conn.cursor()
    cursor.execute("UPDATE chat_sessions SET title = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s AND user_id = %s", (title, session_id, user_id))
    conn.commit()
    cursor.close()

def add_message(session_id: int, role: str, content: str):
    """Add message to session"""
    if DATABASE_URL:
        add_message_pg(session_id, role, content)
    else:
        add_message_sqlite(session_id, role, content)
    
    # Update session timestamp
    if DATABASE_URL:
        update_session_timestamp_pg(session_id)
    else:
        update_session_timestamp_sqlite(session_id)

def add_message_sqlite(session_id: int, role: str, content: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)", (session_id, role, content))
    conn.commit()
    conn.close()

def add_message_pg(session_id: int, role: str, content: str):
    conn = get_pg_connection()
    if not conn:
        add_message_sqlite(session_id, role, content)
        return
    
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_messages (session_id, role, content) VALUES (%s, %s, %s)", (session_id, role, content))
    conn.commit()
    cursor.close()

def update_session_timestamp_sqlite(session_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()

def update_session_timestamp_pg(session_id: int):
    conn = get_pg_connection()
    if not conn:
        update_session_timestamp_sqlite(session_id)
        return
    
    cursor = conn.cursor()
    cursor.execute("UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = %s", (session_id,))
    conn.commit()
    cursor.close()
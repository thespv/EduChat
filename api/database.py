import os
import sqlite3
import json
from pathlib import Path
from datetime import datetime

# Database path for local SQLite
DB_PATH = Path("educhat_history.db")

# PostgreSQL connection (for Render/Production)
DATABASE_URL = os.getenv("DATABASE_URL", "")
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
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT NOT NULL,
            title TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            user TEXT NOT NULL,
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
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id SERIAL PRIMARY KEY,
            "user" TEXT NOT NULL,
            title TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            "user" TEXT NOT NULL,
            name TEXT NOT NULL,
            content TEXT NOT NULL,
            file_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    cursor.close()

def create_session(user: str, title: str = "New Chat") -> int:
    if DATABASE_URL:
        return create_session_pg(user, title)
    return create_session_sqlite(user, title)

def create_session_sqlite(user: str, title: str = "New Chat") -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_sessions (user, title) VALUES (?, ?)", (user, title))
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id

def create_session_pg(user: str, title: str = "New Chat") -> int:
    conn = get_pg_connection()
    if not conn:
        return create_session_sqlite(user, title)
    
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_sessions (\"user\", title) VALUES (%s, %s) RETURNING id", (user, title))
    session_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    return session_id

def get_sessions(user: str) -> list:
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
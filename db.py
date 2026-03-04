import os
import psycopg2
import psycopg2.extras
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_conn():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            subscription_status TEXT DEFAULT 'inactive',
            tank_remaining INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            conversation_phase TEXT DEFAULT 'mirror',
            perceptual_state TEXT,
            opening_problem TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            session_id INTEGER REFERENCES sessions(id),
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            token_count INTEGER,
            model TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS session_outcomes (
            id SERIAL PRIMARY KEY,
            session_id INTEGER REFERENCES sessions(id),
            ending_type TEXT,
            re_examination_ran BOOLEAN,
            re_examination_response TEXT,
            field_widening_detected BOOLEAN
        )
    """)

    conn.commit()
    cur.close()
    conn.close()


def get_or_create_user(email):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    if not user:
        cur.execute(
            "INSERT INTO users (email) VALUES (%s) RETURNING *",
            (email,)
        )
        user = cur.fetchone()
        conn.commit()
    cur.close()
    conn.close()
    return dict(user)


def get_user_by_email(email):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return dict(user) if user else None


def get_user_by_id(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return dict(user) if user else None


def update_user_subscription(email, subscription_status):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET subscription_status = %s WHERE email = %s",
        (subscription_status, email)
    )
    conn.commit()
    cur.close()
    conn.close()


def create_session(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO sessions (user_id, conversation_phase) VALUES (%s, 'mirror') RETURNING *",
        (user_id,)
    )
    session = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return dict(session)


def get_session(session_id, user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM sessions WHERE id = %s AND user_id = %s",
        (session_id, user_id)
    )
    session = cur.fetchone()
    cur.close()
    conn.close()
    return dict(session) if session else None


def get_session_messages(session_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM messages WHERE session_id = %s ORDER BY created_at ASC",
        (session_id,)
    )
    messages = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(m) for m in messages]


def save_message(session_id, role, content, token_count=None, model=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO messages (session_id, role, content, token_count, model) VALUES (%s, %s, %s, %s, %s) RETURNING *",
        (session_id, role, content, token_count, model)
    )
    msg = cur.fetchone()
    cur.execute(
        "UPDATE sessions SET updated_at = NOW() WHERE id = %s",
        (session_id,)
    )
    conn.commit()
    cur.close()
    conn.close()
    return dict(msg)


def set_opening_problem(session_id, content):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE sessions SET opening_problem = %s WHERE id = %s",
        (content, session_id)
    )
    conn.commit()
    cur.close()
    conn.close()

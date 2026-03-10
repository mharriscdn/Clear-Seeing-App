import os
import psycopg2
import psycopg2.extras
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_conn():
    conn = psycopg2.connect(DATABASE_URL,
                            cursor_factory=psycopg2.extras.RealDictCursor)
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

    # Phase engine columns
    cur.execute(
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS entry_charge INTEGER")
    cur.execute(
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS exit_charge INTEGER")
    cur.execute(
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS evasion_count INTEGER DEFAULT 0"
    )
    cur.execute(
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS signal_parse_failed BOOLEAN DEFAULT FALSE"
    )
    cur.execute(
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS phase_signal TEXT"
    )
    cur.execute(
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS old_phase TEXT"
    )
    cur.execute(
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS new_phase TEXT"
    )

    conn.commit()
    cur.close()
    conn.close()


def get_or_create_user(email):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = %s", (email, ))
    user = cur.fetchone()
    if not user:
        cur.execute("INSERT INTO users (email) VALUES (%s) RETURNING *",
                    (email, ))
        user = cur.fetchone()
        conn.commit()
    cur.close()
    conn.close()
    return dict(user)


def get_user_by_email(email):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = %s", (email, ))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return dict(user) if user else None


def get_user_by_id(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = %s", (user_id, ))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return dict(user) if user else None


def update_user_subscription(email, subscription_status):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET subscription_status = %s WHERE email = %s",
                (subscription_status, email))
    conn.commit()
    cur.close()
    conn.close()


def create_session(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO sessions (user_id, conversation_phase) VALUES (%s, 'mirror') RETURNING *",
        (user_id, ))
    session = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return dict(session)


def get_session(session_id, user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sessions WHERE id = %s AND user_id = %s",
                (session_id, user_id))
    session = cur.fetchone()
    cur.close()
    conn.close()
    return dict(session) if session else None


def get_session_messages(session_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM messages WHERE session_id = %s ORDER BY created_at ASC",
        (session_id, ))
    messages = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(m) for m in messages]


def save_message(session_id, role, content, token_count=None, model=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO messages (session_id, role, content, token_count, model) VALUES (%s, %s, %s, %s, %s) RETURNING *",
        (session_id, role, content, token_count, model))
    msg = cur.fetchone()
    cur.execute("UPDATE sessions SET updated_at = NOW() WHERE id = %s",
                (session_id, ))
    conn.commit()
    cur.close()
    conn.close()
    return dict(msg)


def set_opening_problem(session_id, content):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE sessions SET opening_problem = %s WHERE id = %s",
                (content, session_id))
    conn.commit()
    cur.close()
    conn.close()


# ---------------------------------------------------------------------------
# Phase Engine additions
# ---------------------------------------------------------------------------


def update_session_phase(session_id, phase):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE sessions SET conversation_phase = %s, updated_at = NOW() WHERE id = %s",
        (phase, session_id))
    conn.commit()
    cur.close()
    conn.close()


def update_perceptual_state(session_id, state):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE sessions SET perceptual_state = %s WHERE id = %s",
                (state, session_id))
    conn.commit()
    cur.close()
    conn.close()


def increment_evasion_count(session_id):
    """Increments evasion_count and returns the new value."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE sessions SET evasion_count = evasion_count + 1 WHERE id = %s RETURNING evasion_count",
        (session_id, ))
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return row["evasion_count"] if row else 0


def update_session_charge(session_id, field, value):
    """field: 'entry_charge' or 'exit_charge', value: integer 1-10"""
    assert field in ("entry_charge", "exit_charge"), "Invalid charge field"
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"UPDATE sessions SET {field} = %s WHERE id = %s",
                (value, session_id))
    conn.commit()
    cur.close()
    conn.close()


def log_signal_parse_failure(message_id):
    """Marks a message as having no valid phase signal from LLM."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE messages SET signal_parse_failed = TRUE WHERE id = %s",
                (message_id, ))
    conn.commit()
    cur.close()
    conn.close()


def get_signal_failure_rate():
    """
    Returns failure count and total assistant message count.
    Read after 50-100 sessions to validate modular architecture viability.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE signal_parse_failed = TRUE) as failures,
            COUNT(*) as total
        FROM messages
        WHERE role = 'assistant'
    """)
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else {"failures": 0, "total": 0}


def log_signal_transition(message_id, phase_signal, old_phase, new_phase):
    """Records the signal and phase transition for every assistant message."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """UPDATE messages
           SET phase_signal = %s, old_phase = %s, new_phase = %s
           WHERE id = %s""",
        (phase_signal, old_phase, new_phase, message_id),
    )
    conn.commit()
    cur.close()
    conn.close()

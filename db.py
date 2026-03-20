import os
import psycopg2
import psycopg2.extras
from datetime import datetime
from math import ceil

DATABASE_URL = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL")

# ---------------------------------------------------------------------------
# Pricing constants for claude-sonnet-4-6
# ---------------------------------------------------------------------------
_INPUT_RATE       = 3.00  / 1_000_000   # $ per input token
_OUTPUT_RATE      = 15.00 / 1_000_000   # $ per output token
_CACHE_READ_RATE  = 0.30  / 1_000_000   # $ per cache-read token
_MARGIN           = 4                    # 4x actual API cost charged to user
_UNIT_COST        = 0.001               # 1 capacity unit = $0.001 actual cost


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
            capacity_remaining INTEGER DEFAULT 0,
            capacity_reset_date DATE
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
    cur.execute(
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS signal_retry BOOLEAN DEFAULT FALSE"
    )

    # Billing columns — users
    cur.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS capacity_remaining INTEGER DEFAULT 0"
    )
    cur.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS capacity_reset_date DATE"
    )

    # Billing columns — messages
    cur.execute(
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS input_tokens INTEGER"
    )
    cur.execute(
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS output_tokens INTEGER"
    )
    cur.execute(
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS cached_tokens INTEGER"
    )
    cur.execute(
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS capacity_units_deducted INTEGER"
    )

    # Session email column
    cur.execute(
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS reflection_email_sent BOOLEAN DEFAULT FALSE"
    )

    # Disclaimer
    cur.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS disclaimer_acknowledged BOOLEAN DEFAULT FALSE"
    )

    # Titration cycle counter
    cur.execute(
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS titration_cycles INTEGER DEFAULT 0"
    )

    # Trial + Stripe subscription columns
    cur.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMP"
    )
    cur.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT"
    )
    cur.execute(
        "ALTER TABLE users ALTER COLUMN subscription_status SET DEFAULT 'trial'"
    )
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_stripe_customer
        ON users(stripe_customer_id)
    """)

    # Magic link auth tokens
    cur.execute("""
        CREATE TABLE IF NOT EXISTS magic_link_tokens (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_magic_tokens_email
        ON magic_link_tokens(email)
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_magic_token_unique
        ON magic_link_tokens(email, token_hash)
    """)

    conn.commit()
    cur.close()
    conn.close()


def get_or_create_user(email):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = %s", (email, ))
    user = cur.fetchone()
    if not user:
        cur.execute(
            """INSERT INTO users
                   (email, capacity_remaining, subscription_status, trial_ends_at)
               VALUES (%s, 4990, 'trial', NOW() + INTERVAL '7 days')
               RETURNING *""",
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
    session = dict(session)
    import urllib.parse as _up
    _u = _up.urlparse(os.environ.get("DATABASE_URL", ""))
    print(f"[DEBUG create_session] committed session id={session['id']} user_id={user_id} db={_u.hostname}/{_u.path.lstrip('/')}", flush=True)
    return session


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


def save_message(session_id, role, content, token_count=None, model=None,
                 input_tokens=None, output_tokens=None, cached_tokens=None,
                 capacity_units_deducted=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO messages
               (session_id, role, content, token_count, model,
                input_tokens, output_tokens, cached_tokens, capacity_units_deducted)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
        (session_id, role, content, token_count, model,
         input_tokens, output_tokens, cached_tokens, capacity_units_deducted))
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


def set_signal_retry(session_id, value):
    """Sets the signal_retry flag on the session (True when last turn had no signal)."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE sessions SET signal_retry = %s WHERE id = %s",
        (bool(value), session_id),
    )
    conn.commit()
    cur.close()
    conn.close()


def tag_message_old_phase(message_id, phase):
    """Always stamp the phase a message was generated in, regardless of signal detection."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE messages SET old_phase = %s WHERE id = %s",
        (phase, message_id),
    )
    conn.commit()
    cur.close()
    conn.close()


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


# ---------------------------------------------------------------------------
# Capacity / billing
# ---------------------------------------------------------------------------


def deduct_capacity(user_id, input_tokens, output_tokens, cached_tokens):
    """
    Calculates the capacity units for one Claude turn and subtracts them
    from users.capacity_remaining.

    Pricing (claude-sonnet-4-6):
      Input:       $3.00 / 1M tokens
      Output:      $15.00 / 1M tokens
      Cache reads: $0.30 / 1M tokens  (cache_read_input_tokens only)

    4x margin applied; 1 unit = $0.001 actual cost.
    Formula: ceil((actual_cost * 4) / 0.001)

    Returns the integer number of capacity units deducted.
    No floor enforcement — deduct and log; blocking is handled by can_start_session.
    """
    actual_cost = (
        input_tokens  * _INPUT_RATE +
        output_tokens * _OUTPUT_RATE +
        cached_tokens * _CACHE_READ_RATE
    )
    charged_cost = actual_cost * _MARGIN
    capacity_units = ceil(charged_cost / _UNIT_COST)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET capacity_remaining = capacity_remaining - %s WHERE id = %s",
        (capacity_units, user_id),
    )
    conn.commit()
    cur.close()
    conn.close()

    print(
        f"[db] deduct_capacity user={user_id} units={capacity_units} "
        f"(in={input_tokens} out={output_tokens} cached={cached_tokens})"
    )
    return capacity_units


def can_start_session(user_id):
    """
    Returns True if the user has capacity_remaining > 0.
    Called only at session start (first user message in a new session).
    Never called mid-session.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT capacity_remaining FROM users WHERE id = %s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row is None:
        return False
    return row["capacity_remaining"] > 0


def add_capacity_by_email(email, units, set_reset_date=None):
    """
    Adds capacity_units to users.capacity_remaining.
    If set_reset_date is provided, also updates capacity_reset_date.
    Top-up calls pass set_reset_date=None so existing expiry is preserved.
    """
    conn = get_conn()
    cur = conn.cursor()
    if set_reset_date is not None:
        cur.execute(
            """UPDATE users
               SET capacity_remaining = capacity_remaining + %s,
                   capacity_reset_date = %s
               WHERE email = %s""",
            (units, set_reset_date, email),
        )
    else:
        cur.execute(
            "UPDATE users SET capacity_remaining = capacity_remaining + %s WHERE email = %s",
            (units, email),
        )
    conn.commit()
    cur.close()
    conn.close()
    print(f"[db] add_capacity_by_email email={email} units=+{units} reset_date={set_reset_date}")


# ---------------------------------------------------------------------------
# Disclaimer helpers
# ---------------------------------------------------------------------------


def acknowledge_disclaimer(user_id):
    """Marks disclaimer_acknowledged = TRUE for a user. Idempotent."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET disclaimer_acknowledged = TRUE WHERE id = %s",
        (user_id,),
    )
    conn.commit()
    cur.close()
    conn.close()


# ---------------------------------------------------------------------------
# Titration helpers
# ---------------------------------------------------------------------------


def increment_titration_cycles(session_id):
    """
    Increments titration_cycles by 1 and returns the new count.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """UPDATE sessions
           SET titration_cycles = COALESCE(titration_cycles, 0) + 1
           WHERE id = %s
           RETURNING titration_cycles""",
        (session_id,),
    )
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return row["titration_cycles"] if row else 1


# ---------------------------------------------------------------------------
# Session email helpers
# ---------------------------------------------------------------------------


def get_admin_data():
    """Returns users (with session counts) and recent sessions for the admin dashboard."""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            u.id,
            u.email,
            u.created_at,
            u.subscription_status,
            u.trial_ends_at,
            COUNT(s.id) AS session_count
        FROM users u
        LEFT JOIN sessions s ON s.user_id = u.id
        GROUP BY u.id
        ORDER BY u.created_at DESC
    """)
    users = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT
            s.id,
            u.email,
            s.created_at,
            s.opening_problem,
            s.entry_charge,
            s.exit_charge,
            s.conversation_phase
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        ORDER BY s.created_at DESC
        LIMIT 50
    """)
    sessions = [dict(r) for r in cur.fetchall()]

    cur.close()
    conn.close()
    return users, sessions


def get_session_email_data(session_id):
    """
    Returns the structured data needed to generate a post-session reflection email.
    Pulls from sessions, session_outcomes, and users in a single query.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            s.opening_problem,
            s.entry_charge,
            s.exit_charge,
            s.reflection_email_sent,
            so.ending_type,
            u.email AS user_email
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        LEFT JOIN session_outcomes so ON so.session_id = s.id
        WHERE s.id = %s
        """,
        (session_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def mark_reflection_email_sent(session_id):
    """Marks reflection_email_sent = TRUE for a session. Idempotent."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE sessions SET reflection_email_sent = TRUE WHERE id = %s",
        (session_id,),
    )
    conn.commit()
    cur.close()
    conn.close()


# ---------------------------------------------------------------------------
# Trial helpers
# ---------------------------------------------------------------------------


def start_trial(user_id):
    """
    Sets trial_ends_at = NOW() + 7 days and subscription_status = 'trial'
    for a user whose trial_ends_at is currently NULL.
    Safe to call repeatedly — the WHERE clause makes it a no-op if already set.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """UPDATE users
           SET trial_ends_at = NOW() + INTERVAL '7 days',
               subscription_status = 'trial'
           WHERE id = %s AND trial_ends_at IS NULL""",
        (user_id,),
    )
    conn.commit()
    cur.close()
    conn.close()


# ---------------------------------------------------------------------------
# Stripe / subscription helpers
# ---------------------------------------------------------------------------


def get_user_by_stripe_customer_id(stripe_customer_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE stripe_customer_id = %s", (stripe_customer_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return dict(user) if user else None


def update_stripe_customer_id(user_id, stripe_customer_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET stripe_customer_id = %s WHERE id = %s",
        (stripe_customer_id, user_id),
    )
    conn.commit()
    cur.close()
    conn.close()


def update_subscription_by_stripe_customer(stripe_customer_id, status):
    """Updates subscription_status for a user matched by stripe_customer_id."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET subscription_status = %s WHERE stripe_customer_id = %s",
        (status, stripe_customer_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"[db] subscription={status} for stripe_customer={stripe_customer_id}")


# ---------------------------------------------------------------------------
# Magic link token helpers
# ---------------------------------------------------------------------------


def create_magic_token(email, token_hash, expires_at):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO magic_link_tokens (email, token_hash, expires_at)
           VALUES (%s, %s, %s)
           ON CONFLICT (email, token_hash) DO NOTHING""",
        (email, token_hash, expires_at),
    )
    conn.commit()
    cur.close()
    conn.close()


def get_and_use_token(token_hash):
    """
    Atomically finds a valid (unexpired, unused) token, marks it used,
    and returns the record. Returns None if invalid.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """UPDATE magic_link_tokens
           SET used = TRUE
           WHERE token_hash = %s
             AND used = FALSE
             AND expires_at > NOW()
           RETURNING *""",
        (token_hash,),
    )
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return dict(row) if row else None


def cleanup_expired_tokens():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM magic_link_tokens WHERE expires_at < NOW()")
    conn.commit()
    cur.close()
    conn.close()

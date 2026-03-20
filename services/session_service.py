"""
Session service — Phase 2 will add session lifecycle logic here.
For Phase 1 this is a thin wrapper around db calls.

TODO Phase 2: session outcome detection, phase transitions.
"""
import db

OPENING_MESSAGE = "What are you not seeing clearly right now?"


def new_session(user_id):
    """
    Creates a new session, saves the fixed opening assistant message,
    and returns the session record.
    """
    session = db.create_session(user_id)
    db.save_message(session["id"], "assistant", OPENING_MESSAGE, token_count=None, model=None)
    return session

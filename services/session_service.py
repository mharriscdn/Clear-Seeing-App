"""
Session service — Phase 2 will add session lifecycle logic here.
For Phase 1 this is a thin wrapper around db calls.

TODO Phase 2: session outcome detection, phase transitions.
"""
import db

def new_session(user_id):
    """
    Creates a new session and returns the session record.
    The app waits for the user to speak first — no opening message is saved.
    """
    session = db.create_session(user_id)
    return session

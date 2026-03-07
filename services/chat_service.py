"""
Chat service — Phase 2 coaching logic.
Phase engine is now live. Structure enforced by backend, not prompt.
"""
import db
import llm
from services import phase_engine


def process_chat(session_id, user_id, user_message):
    """
    Handles a user message for a given session:
    1. Load session and validate ownership
    2. Save user message
    3. Set opening_problem on first user reply
    4. Build message history for Claude
    5. Call Claude
    6. Save assistant reply
    7. Parse advancement signal
    8. Apply signal to phase engine (update DB phase)
    9. Return (assistant_text, transcript)

    Raises ValueError on bad session.
    """
    session = db.get_session(session_id, user_id)
    if not session:
        raise ValueError("Session not found or access denied")

    existing_messages = db.get_session_messages(session_id)

    # First user reply sets opening_problem
    user_messages = [m for m in existing_messages if m["role"] == "user"]
    is_first_user_reply = len(user_messages) == 0

    # Save user message
    db.save_message(session_id, "user", user_message)

    if is_first_user_reply:
        db.set_opening_problem(session_id, user_message)

    # Build Claude message list
    all_messages = existing_messages + [{
        "role": "user",
        "content": user_message
    }]
    claude_messages = [{
        "role": m["role"],
        "content": m["content"]
    } for m in all_messages]

    # Call Claude — full system prompt every turn (v1)
    assistant_text, token_count, model_name = llm.call_claude(
        claude_messages, session)

    # Save assistant reply — get message_id for signal failure logging
    saved_msg = db.save_message(session_id,
                                "assistant",
                                assistant_text,
                                token_count=token_count,
                                model=model_name)
    message_id = saved_msg["id"]

    # --- PHASE ENGINE ---
    # Reload session to get current state (evasion_count, phase, charges)
    session = db.get_session(session_id, user_id)

    new_phase, signal_found = phase_engine.process_signal(
        session, assistant_text, message_id)

    if not signal_found:
        print(
            f"[chat_service] Signal parse failure — session {session_id}, message {message_id}, phase stayed at {session['conversation_phase']}"
        )

    print(
        f"[chat_service] Phase: {session['conversation_phase']} -> {new_phase}"
    )
    # --- END PHASE ENGINE ---

    transcript = db.get_session_messages(session_id)
    return assistant_text, transcript

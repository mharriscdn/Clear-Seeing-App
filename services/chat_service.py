"""
Chat service — Phase 2 will add coaching logic here (phase sequencing,
modular prompts, outcome tagging). For now, this is a thin pass-through.
"""
import db
import llm


def process_chat(session_id, user_id, user_message):
    """
    Handles a user message for a given session:
    1. Loads session and validates ownership
    2. Saves user message
    3. Checks if this is the user's first reply (sets opening_problem)
    4. Builds message history for Claude
    5. Calls Claude via llm.call_claude()
    6. Saves assistant reply
    Returns (assistant_text, transcript) or raises ValueError on bad session.

    TODO Phase 2: insert phase logic, perceptual state tracking, outcome tagging here.
    """
    session = db.get_session(session_id, user_id)
    if not session:
        raise ValueError("Session not found or access denied")

    existing_messages = db.get_session_messages(session_id)

    # The opening assistant message is always "What's in your central view right now?"
    # Count only user messages to determine if this is the first user reply
    user_messages = [m for m in existing_messages if m["role"] == "user"]
    is_first_user_reply = len(user_messages) == 0

    # Save the user message
    db.save_message(session_id, "user", user_message)

    # Set opening_problem on first user reply
    if is_first_user_reply:
        db.set_opening_problem(session_id, user_message)

    # Build message list for Claude (role/content only)
    all_messages = existing_messages + [{"role": "user", "content": user_message}]
    claude_messages = [{"role": m["role"], "content": m["content"]} for m in all_messages]

    # Call Claude
    assistant_text, token_count, model_name = llm.call_claude(claude_messages, session)

    # Save assistant reply
    db.save_message(session_id, "assistant", assistant_text, token_count=token_count, model=model_name)

    # Return updated transcript
    transcript = db.get_session_messages(session_id)
    return assistant_text, transcript

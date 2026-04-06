"""
Chat service — v9 single-prompt session.

One system prompt. Full conversation history. No phase routing.
"""
import db
import llm


def process_chat(session_id, user_id, user_message):
    """
    Handles a user message for a given session:
    1.  Load session and validate ownership
    2.  Gate: block new session start if capacity_remaining is zero
    3.  Save user message
    4.  Set opening_problem and phase on first user reply
    5.  Build message history for Claude
    6.  Call Claude with v9 session prompt
    7.  Deduct capacity units
    8.  Save assistant reply
    9.  Return (assistant_text, transcript)

    Raises ValueError on bad session or capacity exhausted.
    """
    session = db.get_session(session_id, user_id)
    if not session:
        raise ValueError("Session not found or access denied")

    existing_messages = db.get_session_messages(session_id)

    user_messages = [m for m in existing_messages if m["role"] == "user"]
    is_first_user_reply = len(user_messages) == 0

    if is_first_user_reply and not db.can_start_session(user_id):
        raise ValueError(
            "Your capacity has run out. Visit Manage Billing to top up and continue."
        )

    db.save_message(session_id, "user", user_message)

    if is_first_user_reply:
        db.set_opening_problem(session_id, user_message)
        db.update_session_phase(session_id, "session")

    all_messages = existing_messages + [{"role": "user", "content": user_message}]
    claude_messages = [{"role": m["role"], "content": m["content"]} for m in all_messages]

    result = llm.call_claude(claude_messages)
    assistant_text = result["content"]
    input_tokens   = result["input_tokens"]
    output_tokens  = result["output_tokens"]
    cached_tokens  = result["cached_tokens"]
    model_name     = result["model"]

    capacity_units = db.deduct_capacity(user_id, input_tokens, output_tokens, cached_tokens)

    db.save_message(
        session_id,
        "assistant",
        assistant_text,
        token_count=input_tokens + output_tokens,
        model=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        capacity_units_deducted=capacity_units,
    )

    transcript = db.get_session_messages(session_id)
    return assistant_text, transcript

"""
Chat service — Phase 2 coaching logic.
Phase engine is now live. Structure enforced by backend, not prompt.
"""
import re
import db
import llm
from services import phase_engine


def _try_capture_entry_charge(session_id, session, existing_messages, user_message):
    """
    During the mirror phase, capture the user's charge rating and persist it.

    Conditions required before extracting:
      - Session is still in 'mirror' phase
      - entry_charge has not yet been recorded
      - At least one assistant message exists (the mirror has been delivered)

    Extracts the first integer 1–10 found in the user message.
    """
    if session.get("conversation_phase") != "mirror":
        return
    if session.get("entry_charge") is not None:
        return
    assistant_messages = [m for m in existing_messages if m["role"] == "assistant"]
    if not assistant_messages:
        return

    match = re.search(r'\b(10|[1-9])\b', user_message)
    if match:
        charge = int(match.group(1))
        db.update_session_charge(session_id, "entry_charge", charge)
        print(f"[chat_service] entry_charge captured: {charge} (session {session_id})")


def _try_capture_exit_charge(session_id, session, existing_messages, user_message):
    """
    During the re_examination phase, capture the user's exit charge rating.

    Conditions required before extracting:
      - Session is in 're_examination' phase
      - exit_charge has not yet been recorded
      - At least one assistant message exists (the re-examination question has been asked)

    Extracts the first integer 1–10 found in the user message.
    """
    if session.get("conversation_phase") != "re_examination":
        return
    if session.get("exit_charge") is not None:
        return
    assistant_messages = [m for m in existing_messages if m["role"] == "assistant"]
    if not assistant_messages:
        return

    match = re.search(r'\b(10|[1-9])\b', user_message)
    if match:
        charge = int(match.group(1))
        db.update_session_charge(session_id, "exit_charge", charge)
        print(f"[chat_service] exit_charge captured: {charge} (session {session_id})")


def charge_delta_summary(entry_charge, exit_charge):
    """
    Returns a one-line closing reference to both charge numbers.
    Used by Claude (via prompt instruction) and directly testable.

      charge dropped  → "You came in at {entry}. You're at {exit} now."
      charge same     → "You came in at {entry}. Still at {exit}. The charge held."
      charge rose     → "You came in at {entry}. It's at {exit}. The system tightened."
    """
    if exit_charge < entry_charge:
        return f"You came in at {entry_charge}. You're at {exit_charge} now."
    elif exit_charge == entry_charge:
        return f"You came in at {entry_charge}. Still at {exit_charge}. The charge held."
    else:
        return f"You came in at {entry_charge}. It's at {exit_charge}. The system tightened."


# Injected when phase transitions into re_examination — guarantees the charge
# question fires without depending on Claude to remember it.
_RE_EXAM_CHARGE_QUESTION = "What's the charge now, on a scale of 1 to 10?"


def process_chat(session_id, user_id, user_message):
    """
    Handles a user message for a given session:
    1.  Load session and validate ownership
    2.  Gate: block new session start if capacity_remaining is zero
    3.  Save user message
    4.  Set opening_problem on first user reply
    5.  Build message history for Claude
    6.  Call Claude
    7.  Deduct capacity units
    8.  Save assistant reply with full token data
    9.  Parse advancement signal
    10. Apply signal to phase engine (update DB phase)
    11. If phase just entered re_examination, inject exit-charge question
    12. Log signal transition
    13. Return (assistant_text, transcript)
    Raises ValueError on bad session.
    """
    session = db.get_session(session_id, user_id)
    if not session:
        raise ValueError("Session not found or access denied")

    signal_retry = session.get("signal_retry", False)

    existing_messages = db.get_session_messages(session_id)

    # First user reply sets opening_problem and triggers session gate
    user_messages = [m for m in existing_messages if m["role"] == "user"]
    is_first_user_reply = len(user_messages) == 0

    # Session gate — checked only at session start, never mid-session
    if is_first_user_reply and not db.can_start_session(user_id):
        return (
            "Your capacity has run out. Visit your account to top up and continue.",
            [],
        )

    # Save user message
    db.save_message(session_id, "user", user_message)

    if is_first_user_reply:
        db.set_opening_problem(session_id, user_message)

    # Capture entry_charge if the user just answered the charge question
    _try_capture_entry_charge(session_id, session, existing_messages, user_message)

    # Capture exit_charge if the user just answered the re-examination charge question
    _try_capture_exit_charge(session_id, session, existing_messages, user_message)

    # Build Claude message list
    all_messages = existing_messages + [{"role": "user", "content": user_message}]
    claude_messages = [{"role": m["role"], "content": m["content"]} for m in all_messages]

    # Call Claude — returns token dict
    result = llm.call_claude(claude_messages, session, signal_retry=signal_retry)
    assistant_text  = result["content"]
    input_tokens    = result["input_tokens"]
    output_tokens   = result["output_tokens"]
    cached_tokens   = result["cached_tokens"]
    model_name      = result["model"]

    # Deduct capacity — single computed value used for both deduction and logging
    capacity_units = db.deduct_capacity(user_id, input_tokens, output_tokens, cached_tokens)

    # Save assistant reply with full token data
    saved_msg = db.save_message(
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
    message_id = saved_msg["id"]

    # --- PHASE ENGINE ---
    # Reload session to get current state (evasion_count, phase, charges)
    session = db.get_session(session_id, user_id)
    old_phase = session["conversation_phase"]

    new_phase, signal_found, signal = phase_engine.process_signal(
        session, assistant_text, message_id
    )

    # --- SIGNAL RETRY FLAG ---
    db.set_signal_retry(session_id, not signal_found)

    # --- SIGNAL LOGGING ---
    if signal_found:
        db.log_signal_transition(message_id, signal, old_phase, new_phase)
    else:
        print(
            f"[chat_service] Signal parse failure — session {session_id}, "
            f"message {message_id}, phase stayed at {old_phase}"
        )

    print(
        f"[chat_service] signal={signal} | phase: {old_phase} -> {new_phase}"
    )
    # --- END PHASE ENGINE ---

    # --- EXIT CHARGE INJECTION ---
    # When the phase first enters re_examination, inject the charge question
    # directly as a backend message. This guarantees the question fires every
    # time, without relying on Claude to remember it.
    if new_phase == "re_examination" and old_phase != "re_examination":
        db.save_message(session_id, "assistant", _RE_EXAM_CHARGE_QUESTION)
        assistant_text = assistant_text.rstrip() + "\n\n" + _RE_EXAM_CHARGE_QUESTION
        print(f"[chat_service] Exit charge question injected (session {session_id})")
    # --- END EXIT CHARGE INJECTION ---

    transcript = db.get_session_messages(session_id)
    return assistant_text, transcript

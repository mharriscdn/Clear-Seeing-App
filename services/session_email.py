"""
Post-session reflection email service.

Triggered when a session reaches recurrence_normalization phase.
Generates a personalised reflection email via Claude, then sends it
via Resend. Fires at most once per session — guarded by the
reflection_email_sent flag on the sessions table.
"""
import os
import anthropic
import requests
from datetime import datetime

import db

MODEL = "claude-sonnet-4-6"

_SYSTEM = (
    "You are generating a post-session reflection email for a user of the "
    "Clear Seeing app. Be brief, observational, and match this tone: direct, "
    "no therapy language, no praise, no interpretation. "
    "Use the user's own words where possible."
)

_WHY_RETURN = (
    "The patterns that fired today did not form overnight. They formed through "
    "repetition — thousands of small moments where the nervous system learned "
    "to brace against something it predicted would be dangerous. Clear Seeing "
    "works the same way, in reverse. Each time both forces are held and the "
    "charge releases, the nervous system updates its prediction. The grip "
    "loosens. Not through insight. Through repetition. Use it when you are not "
    "seeing clearly. That is the right moment."
)

_FEEDBACK_ASK = "How was this session? Reply to this email — I read every one."


def _extract_mirror_turn(messages):
    """
    Returns the content of the first assistant message that follows the
    first user message (i.e. the mirror delivery).
    Returns an empty string if not found.
    """
    found_first_user = False
    for m in messages:
        if m["role"] == "user" and not found_first_user:
            found_first_user = True
            continue
        if found_first_user and m["role"] == "assistant":
            return m["content"]
    return ""


def _extract_hold_both_forces_turn(messages):
    """
    Returns the content of the assistant message delivered during the
    hold_both_forces phase.

    log_signal_transition() sets old_phase on the message that advanced
    the session *away* from hold_both_forces — that message was generated
    while Claude was in that phase.  Falls back to empty string.
    """
    for m in messages:
        if m.get("old_phase") == "hold_both_forces" and m["role"] == "assistant":
            return m["content"]
    return ""


def _build_prompt(data, mirror_text, forces_text):
    """Assembles the user-facing prompt string for Claude."""
    ending_type = data.get("ending_type") or "path_b"
    entry = data.get("entry_charge")
    exit_charge = data.get("exit_charge") or 0

    if ending_type == "path_a":
        what_shifted = "PATH A: 'The pattern was seen clearly. That is real work.'"
    elif ending_type == "path_c":
        what_shifted = "PATH C: 'The prediction was tested and failed to land.'"
    else:
        what_shifted = (
            f"PATH B: 'You came in at {entry}. "
            f"You left at {exit_charge}. Same situation — wider field.'"
        )

    return (
        "Generate a reflection email using this session data:\n"
        f"Opening problem: {data.get('opening_problem') or '(not recorded)'}\n"
        f"Escape pattern observed: {mirror_text or '(not available)'}\n"
        f"Two forces held: {forces_text or '(not available)'}\n"
        f"Entry charge: {entry}/10\n"
        f"Exit charge: {exit_charge}/10 (null if PATH A)\n"
        f"Session outcome: {ending_type}\n"
        "\n"
        "Structure the email with these exact sections:\n"
        "1. What you brought — one sentence using their words\n"
        "2. What the mind was doing — one sentence naming the escape pattern\n"
        "3. The two forces — one sentence describing what was held\n"
        f"4. What shifted — one or two sentences using charge numbers. {what_shifted}\n"
        f"5. Why coming back matters — use this exact text:\n'{_WHY_RETURN}'\n"
        f"6. Feedback ask — use this exact text:\n'{_FEEDBACK_ASK}'\n"
        "\n"
        "Return only the email body text. No subject line. No preamble."
    )


def _call_claude(prompt_text):
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model=MODEL,
        max_tokens=500,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt_text}],
    )
    return response.content[0].text.strip()


def _send_via_resend(to_email, subject, body):
    api_key = os.environ.get("RESEND_API_KEY")
    from_addr = os.environ.get("EMAIL_FROM")
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "from": from_addr,
            "to": to_email,
            "reply_to": "mharriscdn@gmail.com",
            "subject": subject,
            "text": body,
        },
        timeout=15,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Resend error {resp.status_code}: {resp.text}"
        )


def send_session_email(session_id):
    """
    Generates and sends the post-session reflection email for session_id.

    Guards:
    - Does nothing if reflection_email_sent is already TRUE (double-fire guard).
    - Logs and swallows all errors — session completion must never depend on
      email success.
    """
    try:
        data = db.get_session_email_data(session_id)
        if not data:
            print(f"[session_email] No data found for session {session_id}")
            return

        if data.get("reflection_email_sent"):
            print(f"[session_email] Already sent for session {session_id} — skipping")
            return

        messages = db.get_session_messages(session_id)
        mirror_text = _extract_mirror_turn(messages)
        forces_text = _extract_hold_both_forces_turn(messages)

        prompt = _build_prompt(data, mirror_text, forces_text)
        email_body = _call_claude(prompt)

        date_str = datetime.utcnow().strftime("%-d %B %Y")
        subject = f"Your Clear Seeing session — {date_str}"

        _send_via_resend(data["user_email"], subject, email_body)

        db.mark_reflection_email_sent(session_id)
        print(f"[session_email] Sent to {data['user_email']} for session {session_id}")

    except Exception as e:
        print(f"[session_email] ERROR (non-fatal) for session {session_id}: {e}")

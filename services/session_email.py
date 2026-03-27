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
    "Clear Seeing app. Be brief, observational, direct. No therapy language. "
    "No praise. No interpretation. Use the user's own words where possible. "
    "If data for a section is missing or null, omit that section entirely — "
    "never mention what the session didn't reach or what wasn't captured."
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

_FEEDBACK_ASK = "If something is still live after reading this — come back."


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


def _build_prompt(data, forces_text):
    """Assembles the user-facing prompt string for Claude."""
    ending_type = data.get("ending_type") or "incomplete"
    entry = data.get("entry_charge")
    exit_charge = data.get("exit_charge")

    if ending_type == "path_a":
        what_shifted = (
            "PATH A: The session ended before both forces could be held. "
            "Come back when something is live."
        )
    elif ending_type == "path_c" and exit_charge is not None:
        what_shifted = (
            f"PATH C: You came in at {entry}. You left at {exit_charge}. "
            "The verdict had nothing to hit."
        )
    elif ending_type == "path_b" and exit_charge is not None:
        what_shifted = (
            f"PATH B: You came in at {entry}. You left at {exit_charge}. "
            "Same situation — wider field."
        )
    else:
        what_shifted = None

    exit_charge_display = f"{exit_charge}/10" if exit_charge is not None else "null (not reached)"

    return (
        "Generate a reflection email using this session data:\n\n"
        f"Opening problem: {data.get('opening_problem') or 'not captured'}\n"
        f"Exit door (escape pattern): {data.get('exit_door') or 'not captured'}\n"
        f"Horror film type: {data.get('horror_film') or 'not captured'}\n"
        f"Entry charge: {entry}/10\n"
        f"Exit charge: {exit_charge_display}\n"
        f"Session outcome: {ending_type}\n"
        f"Two forces held: {forces_text or 'not captured'}\n"
        "\n"
        "Rules:\n"
        "- Only include a section if the data for it exists and is meaningful\n"
        "- Never mention what the session didn't reach\n"
        "- Never describe the app's internal behavior to the user\n"
        "- Never fabricate a charge number — if exit charge is null, do not include a charge comparison\n"
        "\n"
        "Use plain text section headers with no markdown, no asterisks, no bold "
        "formatting. Separate sections with a blank line only.\n"
        "\n"
        "Use this structure, omitting any section where data is missing:\n"
        "\n"
        "1. What you brought\n"
        "One sentence using their exact words from the opening problem.\n"
        "\n"
        "2. What the mind was doing\n"
        "One sentence naming the escape pattern using plain language.\n"
        "Exit door labels translate as:\n"
        "analyzing → going over it, trying to figure it out\n"
        "seeking_reassurance → looking for confirmation it will be okay\n"
        "reframing → trying to see it differently\n"
        "catastrophizing → running it forward, stacking worst cases\n"
        "excavating_past → tracing it back to where it started\n"
        "comparing_progress → measuring against where you should be\n"
        "seeking_certainty → needing to know how it turns out\n"
        "meta_observing → watching yourself experience it\n"
        "\n"
        "3. The two forces [only if hold_both_forces phase was reached]\n"
        "One sentence describing what was held — gas toward resolution, "
        "brake against the verdict landing. Use their specific content.\n"
        "\n"
        "4. What shifted [only if exit charge exists]\n"
        + (what_shifted if what_shifted else "(omit this section)") +
        "\n"
        "\n"
        "5. Why coming back matters\n"
        f"{_WHY_RETURN}\n"
        "\n"
        f"{_FEEDBACK_ASK}\n"
        "\n"
        "Return only the email body. No subject line. No preamble."
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
        forces_text = _extract_hold_both_forces_turn(messages)

        prompt = _build_prompt(data, forces_text)
        email_body = _call_claude(prompt)
        email_body = email_body.replace("**", "").replace("__", "")

        date_str = datetime.utcnow().strftime("%-d %B %Y")
        subject = f"Your Clear Seeing session — {date_str}"

        _send_via_resend(data["user_email"], subject, email_body)

        db.mark_reflection_email_sent(session_id)
        print(f"[session_email] Sent to {data['user_email']} for session {session_id}")

    except Exception as e:
        print(f"[session_email] ERROR (non-fatal) for session {session_id}: {e}")

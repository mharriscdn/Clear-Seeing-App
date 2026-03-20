import os
from datetime import datetime

from dotenv import load_dotenv
load_dotenv(override=True)

print("[startup] DATABASE_URL:", os.environ.get("DATABASE_URL", "")[:50])

import jwt as pyjwt
from flask import Flask, request, jsonify, render_template, redirect, send_file
from werkzeug.middleware.proxy_fix import ProxyFix

import db
import auth_magic_link
import stripe_webhooks
from services import chat_service, session_service, billing_service, session_email

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")

# ProxyFix is required so url_for() generates https:// URLs correctly behind Replit's proxy
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Register magic link auth blueprint at /auth prefix
app.register_blueprint(auth_magic_link.bp, url_prefix="/auth")

# Initialize database tables on startup
try:
    db.init_db()
except Exception as e:
    print("DB init failed:", e)

# Keep prompt master doc current on every deploy
try:
    import subprocess, sys
    subprocess.run([sys.executable, "docs/generate_prompt_master.py"], check=True)
except Exception as e:
    print("Prompt master generation failed:", e)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_user_from_cookie():
    """
    Decodes the JWT session cookie and returns the DB user dict, or None.
    Used for routes that need the user but aren't wrapped in require_auth.
    """
    token = request.cookies.get("cs_session")
    if not token:
        return None
    try:
        payload = pyjwt.decode(
            token, os.environ.get("JWT_SECRET", ""), algorithms=["HS256"]
        )
        return db.get_user_by_id(payload.get("user_id"))
    except Exception:
        return None


def _check_access(user):
    """
    Returns True if the user may access the main app.

    Rules:
    - Active subscription → allow.
    - trial_ends_at is NULL → trial not yet started; initialize it now and allow.
    - trial_ends_at is set and in the future → allow.
    - trial_ends_at is set and in the past → deny (redirect to paywall).
    """
    if user.get("subscription_status") == "active":
        return True

    trial_ends = user.get("trial_ends_at")

    if trial_ends is None:
        # Trial never initialized (pre-existing user or race condition).
        # Start it now — safe to call repeatedly; DB only updates if still NULL.
        db.start_trial(user["id"])
        return True

    # trial_ends_at is set — check whether it's still valid.
    if isinstance(trial_ends, str):
        trial_ends = datetime.fromisoformat(trial_ends)
    if datetime.utcnow() < trial_ends.replace(tzinfo=None):
        return True

    return False


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.route("/health")
def health():
    return "OK", 200


# ---------------------------------------------------------------------------
# Frontend — access-gated
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    user = _get_user_from_cookie()
    if user is None:
        return redirect("/login")
    if not _check_access(user):
        return redirect("/paywall")
    return render_template("index.html")


@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/paywall")
def paywall():
    user = _get_user_from_cookie()
    if user is None:
        return redirect("/login")
    if _check_access(user):
        return redirect("/")
    return render_template("paywall.html")


# ---------------------------------------------------------------------------
# Stripe — subscription checkout from paywall
# ---------------------------------------------------------------------------


@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    user = _get_user_from_cookie()
    if user is None:
        return redirect("/login")

    price_id = os.environ.get("STRIPE_PRICE_ID_STANDARD")
    if not price_id:
        return "Subscription price not configured.", 500

    success_url = "https://app.clearseeing.ca"
    cancel_url = "https://app.clearseeing.ca/paywall"

    try:
        session = stripe_webhooks.create_paywall_checkout(
            user, price_id, success_url, cancel_url
        )
        return redirect(session.url, code=303)
    except Exception as e:
        print(f"[create_checkout_session] Stripe error: {e}")
        return "Failed to start checkout. Please try again.", 500


# ---------------------------------------------------------------------------
# API — Auth / User
# ---------------------------------------------------------------------------


@app.route("/api/me")
@auth_magic_link.require_auth
def api_me():
    user = request.current_user
    return jsonify({
        "email": user["email"],
        "subscription_status": user["subscription_status"],
        "capacity_remaining": user["capacity_remaining"],
    })


# ---------------------------------------------------------------------------
# API — Sessions
# ---------------------------------------------------------------------------


@app.route("/api/session/new", methods=["POST"])
@auth_magic_link.require_auth
def api_new_session():
    user = request.current_user
    s = session_service.new_session(user["id"])
    return jsonify({"session_id": s["id"]})


# ---------------------------------------------------------------------------
# Hold-both-forces check-in / titration helpers
# ---------------------------------------------------------------------------

_CHECKIN_Q = (
    "How is the charge right now \u2014 manageable, or feeling like too much? "
    "Type A or B."
)
_STAY_MSG = (
    "Good. Stay with both again. Give it 60\u2013120 seconds or more. "
    "Type \u2018continue\u2019 when ready."
)
_TITRATION = (
    "The charge is high. That\u2019s the system doing its job \u2014 protecting "
    "against something it predicts will be dangerous.\n\n"
    "This is how capacity builds: not through insight, but through contact. "
    "Each round, the nervous system learns it survived. That\u2019s titration.\n\n"
    "First contact \u2014 the system braces.\n"
    "Second contact \u2014 it starts to recognize it didn\u2019t get damaged.\n"
    "Third contact \u2014 the grip begins to loosen.\n\n"
    "You don\u2019t need to push through. You just need to make contact, "
    "again and again.\n\n"
    "Which of these feels right? Type A, B, C, or D:\n\n"
    "A) Touch just the edge \u2014 stay at the boundary, not the center\n"
    "B) Anchor outward \u2014 keep the feeling, add something external "
    "(a sound, the vast space around the charge, a pink filter)\n"
    "C) Let it fill you completely for 10 seconds, then check\n"
    "D) Break state \u2014 go for a walk, splash cold water, change rooms. "
    "Come back when the intensity drops \u2014 not when it\u2019s gone, "
    "just more manageable."
)
_AFTER_CYCLE = (
    "Each round builds capacity. This is exactly how it works.\n"
    "How is the charge now \u2014 ready to continue, another round of "
    "the same, or a different option? Type A, B, or C.\n"
    "A) Continue \u2014 back to holding both forces\n"
    "B) Another round of the same\n"
    "C) Different option"
)
_THREE_CYCLES = (
    "You\u2019ve done three rounds. That\u2019s real work. The system is "
    "building capacity right now whether it feels like it or not.\n"
    "Two options:\n"
    "A) Stay with both forces again\n"
    "B) Close the session and come back when something is live"
)


def _make_transcript(messages):
    return [
        {"role": m["role"], "content": m["content"], "created_at": str(m["created_at"])}
        for m in messages
    ]


def _system_reply(session_id, user_msg_to_save, assistant_text):
    """
    Saves an optional user message then the assistant text, and returns a
    full JSON response. Phase stays hold_both_forces (no Claude call made).
    """
    if user_msg_to_save is not None:
        db.save_message(session_id, "user", user_msg_to_save)
    db.save_message(session_id, "assistant", assistant_text)
    transcript = db.get_session_messages(session_id)
    return jsonify({
        "assistant_text": assistant_text,
        "current_phase": "hold_both_forces",
        "transcript": _make_transcript(transcript),
    })


def _handle_hold_both_forces(session_id, session_state, user_message):
    """
    Intercepts check-in and titration messages in hold_both_forces phase.
    Returns a Flask response if intercepted, None to fall through to Claude.
    """
    if session_state.get("conversation_phase") != "hold_both_forces":
        return None

    msg       = user_message.strip()
    msg_lower = msg.lower()
    cycles    = session_state.get("titration_cycles") or 0

    messages  = db.get_session_messages(session_id)
    last_asst = next(
        (m["content"] for m in reversed(messages) if m["role"] == "assistant"), ""
    ).strip()

    # Invisible system heartbeat — no user message saved
    if msg == "__checkin__":
        return _system_reply(session_id, None, _CHECKIN_Q)

    # Response to the charge check-in "Type A or B"
    if last_asst == _CHECKIN_Q:
        if msg_lower == "a":
            return _system_reply(session_id, msg, _STAY_MSG)
        if msg_lower == "b":
            new_cycles = db.increment_titration_cycles(session_id)
            reply = _THREE_CYCLES if new_cycles >= 3 else _TITRATION
            return _system_reply(session_id, msg, reply)
        # Any other reply: fall through to Claude

    # Response to after-cycle menu "Type A, B, or C"
    if last_asst.startswith("Each round builds capacity"):
        if msg_lower == "b":
            return _system_reply(session_id, msg, _TITRATION)
        if msg_lower == "c":
            return _system_reply(session_id, msg, _TITRATION)
        # A or anything else: fall through to Claude

    return None  # normal Claude flow


# ---------------------------------------------------------------------------
# API — Chat
# ---------------------------------------------------------------------------


@app.route("/api/chat", methods=["POST"])
@auth_magic_link.require_auth
def api_chat():
    user = request.current_user
    data = request.get_json()
    session_id = data.get("session_id")
    user_message = data.get("user_message", "").strip()

    if not session_id or not user_message:
        return jsonify({"error": "session_id and user_message are required"}), 400

    # Load session state up front — needed for hold_both_forces intercept
    session_state = db.get_session(session_id, user["id"])
    if not session_state:
        return jsonify({"error": "Session not found"}), 403

    # Hold_both_forces intercept — check-in / titration (no Claude call)
    intercept = _handle_hold_both_forces(session_id, session_state, user_message)
    if intercept is not None:
        return intercept

    # Normal path: call Claude
    try:
        assistant_text, transcript = chat_service.process_chat(
            session_id, user["id"], user_message)
    except ValueError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        print(f"[api_chat] Error: {e}")
        return jsonify({"error": "Failed to get response from Claude"}), 500

    # Reload session state (phase may have changed after process_chat)
    try:
        session_state = db.get_session(session_id, user["id"])
        if (
            session_state
            and session_state.get("conversation_phase") == "recurrence_normalization"
            and not session_state.get("reflection_email_sent")
        ):
            session_email.send_session_email(session_id)
    except Exception as e:
        print(f"[api_chat] Reflection email trigger error (non-fatal): {e}")

    current_phase = session_state.get("conversation_phase") if session_state else None

    return jsonify({
        "assistant_text": assistant_text,
        "current_phase": current_phase,
        "transcript": _make_transcript(transcript),
    })


# ---------------------------------------------------------------------------
# API — Billing (Stripe)
# ---------------------------------------------------------------------------


@app.route("/api/billing/checkout", methods=["POST"])
@auth_magic_link.require_auth
def api_checkout():
    user = request.current_user
    data = request.get_json()
    plan = data.get("plan", "standard")

    base_url = request.host_url.rstrip("/")
    success_url = f"{base_url}/?checkout=success"
    cancel_url = f"{base_url}/?checkout=cancel"

    try:
        checkout_url = billing_service.get_checkout_url(
            user["email"], plan, success_url, cancel_url)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"[api_checkout] Stripe error: {e}")
        return jsonify({"error": "Failed to create checkout session"}), 500

    return jsonify({"url": checkout_url})


@app.route("/api/billing/portal", methods=["POST"])
@auth_magic_link.require_auth
def api_portal():
    user = request.current_user
    base_url = request.host_url.rstrip("/")
    return_url = f"{base_url}/"

    try:
        portal_url = billing_service.get_portal_url(user["email"], return_url)
    except Exception as e:
        print(f"[api_portal] Stripe error: {e}")
        return jsonify({"error": "Failed to create portal session"}), 500

    if not portal_url:
        return jsonify({"error": "No Stripe customer found for this account"}), 404

    return jsonify({"url": portal_url})


@app.route("/api/stripe/webhook", methods=["POST"])
def api_stripe_webhook():
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature")
    result, status = stripe_webhooks.handle_webhook(payload, sig_header)
    return jsonify(result), status


# ---------------------------------------------------------------------------
# Admin dashboard
# ---------------------------------------------------------------------------

_ADMIN_EMAIL = "mharriscdn@gmail.com"

@app.route("/admin")
@auth_magic_link.require_auth
def admin():
    if request.current_user["email"] != _ADMIN_EMAIL:
        return "Forbidden", 403
    users, sessions = db.get_admin_data()
    return render_template("admin.html", users=users, sessions=sessions)


# ---------------------------------------------------------------------------
# TEMPORARY FILE DOWNLOAD — remove after use
# ---------------------------------------------------------------------------

@app.route("/admin/download/db-safety")
def admin_download_db_safety():
    user = _get_user_from_cookie()
    if user is None:
        return jsonify({"error": "Unauthorized"}), 401
    return send_file(
        "docs/db_safety.docx",
        as_attachment=True,
        download_name="clear_seeing_db_safety_v1.docx",
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)

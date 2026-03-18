import os
from datetime import datetime

import jwt as pyjwt
from flask import Flask, request, jsonify, render_template, redirect
from werkzeug.middleware.proxy_fix import ProxyFix

import db
import auth_magic_link
import stripe_webhooks
from services import chat_service, session_service, billing_service

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


# TEMPORARY — remove after use
@app.route("/api/admin/fix-developer-account", methods=["POST"])
@auth_magic_link.require_auth
def admin_fix_developer_account():
    import psycopg2, psycopg2.extras
    conn = psycopg2.connect(os.environ["DATABASE_URL"],
                            cursor_factory=psycopg2.extras.RealDictCursor)
    cur = conn.cursor()
    cur.execute("""
        UPDATE users
        SET subscription_status = 'active', trial_ends_at = NULL
        WHERE email = 'mharriscdn@gmail.com'
    """)
    rows_updated = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True, "rows_updated": rows_updated,
                    "email": "mharriscdn@gmail.com",
                    "subscription_status": "active"})


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
    # If they now have access (e.g. webhook already fired), send them home
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

    try:
        assistant_text, transcript = chat_service.process_chat(
            session_id, user["id"], user_message)
    except ValueError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        print(f"[api_chat] Error: {e}")
        return jsonify({"error": "Failed to get response from Claude"}), 500

    return jsonify({
        "assistant_text": assistant_text,
        "transcript": [{
            "role": m["role"],
            "content": m["content"],
            "created_at": str(m["created_at"])
        } for m in transcript],
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)

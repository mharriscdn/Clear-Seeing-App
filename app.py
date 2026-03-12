import os
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from werkzeug.middleware.proxy_fix import ProxyFix
import db
import auth
from replit_auth import make_replit_blueprint, init_login_manager, require_login
from services import chat_service, session_service, billing_service
import stripe_webhooks

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")

# ProxyFix is required so url_for() generates https:// URLs correctly behind Replit's proxy
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Register Replit OIDC auth blueprint at /auth prefix
app.register_blueprint(make_replit_blueprint(), url_prefix="/auth")
init_login_manager(app)

# Initialize database tables on startup
try:
    db.init_db()
except Exception as e:
    print("DB init failed:", e)


@app.route("/health")
def health():
    return "OK", 200


@app.before_request
def make_session_permanent():
    session.permanent = True


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# API — Auth / User
# ---------------------------------------------------------------------------


@app.route("/api/me")
@auth.require_auth
def api_me():
    user = request.current_user
    return jsonify({
        "email": user["email"],
        "subscription_status": user["subscription_status"],
        "tank_remaining": user["tank_remaining"],
    })


# ---------------------------------------------------------------------------
# API — Sessions
# ---------------------------------------------------------------------------


@app.route("/api/session/new", methods=["POST"])
@auth.require_auth
def api_new_session():
    user = request.current_user
    s = session_service.new_session(user["id"])
    return jsonify({"session_id": s["id"]})


# ---------------------------------------------------------------------------
# API — Chat
# ---------------------------------------------------------------------------


@app.route("/api/chat", methods=["POST"])
@auth.require_auth
def api_chat():
    user = request.current_user
    data = request.get_json()
    session_id = data.get("session_id")
    user_message = data.get("user_message", "").strip()

    if not session_id or not user_message:
        return jsonify({"error":
                        "session_id and user_message are required"}), 400

    try:
        assistant_text, transcript = chat_service.process_chat(
            session_id, user["id"], user_message)
    except ValueError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        print(f"[api_chat] Error: {e}")
        return jsonify({"error": "Failed to get response from Claude"}), 500

    return jsonify({
        "assistant_text":
        assistant_text,
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
@auth.require_auth
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
@auth.require_auth
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
        return jsonify({"error":
                        "No Stripe customer found for this account"}), 404

    return jsonify({"url": portal_url})


@app.route("/api/stripe/webhook", methods=["POST"])
def api_stripe_webhook():
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature")
    result, status = stripe_webhooks.handle_webhook(payload, sig_header)
    return jsonify(result), status


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)

"""
auth_magic_link.py — Magic link email authentication.

Blueprint mounts at /auth prefix in app.py.
Routes:
    POST /auth/request-link  — send login email
    GET  /auth/verify        — consume token, issue JWT cookie
    GET  /auth/logout        — clear session cookie

Decorator:
    require_auth — validates JWT cookie, attaches user to request.current_user
"""

import os
import secrets
import hashlib
import datetime
from functools import wraps

import jwt
import requests
from flask import (
    Blueprint,
    request,
    redirect,
    render_template,
    make_response,
    jsonify,
)

import db

bp = Blueprint("magic_link", __name__)

_COOKIE_NAME = "cs_session"
_COOKIE_MAX_AGE = 60 * 60 * 24  # 24 hours in seconds


def _resend_key():
    return os.environ.get("RESEND_API_KEY", "")


def _email_from():
    return os.environ.get("EMAIL_FROM", "noreply@clearseeing.ca")


def _jwt_secret():
    return os.environ.get("JWT_SECRET", "")


def _expiry_minutes():
    return int(os.environ.get("MAGIC_LINK_EXPIRY_MINUTES", "15"))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@bp.route("/request-link", methods=["POST"])
def request_link():
    email = request.form.get("email", "").strip().lower()
    if not email or "@" not in email:
        return render_template("login.html", error="Please enter a valid email address.")

    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expiry = _expiry_minutes()
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=expiry)

    db.create_magic_token(email, token_hash, expires_at)

    base = request.host_url.rstrip("/")
    verify_url = f"{base}/auth/verify?token={token}"

    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {_resend_key()}",
                "Content-Type": "application/json",
            },
            json={
                "from": _email_from(),
                "to": [email],
                "subject": "Your Clear Seeing login link",
                "html": (
                    f"<p>Click to log in to Clear Seeing:</p>"
                    f"<p><a href='{verify_url}'>Log in</a></p>"
                    f"<p>This link expires in {expiry} minutes. "
                    f"If you did not request this, ignore this email.</p>"
                ),
            },
            timeout=10,
        )
        if resp.status_code not in (200, 201):
            print(f"[magic_link] Resend error {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[magic_link] Email send failed: {e}")

    return render_template("login.html", sent=True)


@bp.route("/verify", methods=["GET"])
def verify():
    raw_token = request.args.get("token", "")
    if not raw_token:
        return render_template("login.html", error="Invalid or missing login link.")

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    record = db.get_and_use_token(token_hash)

    if not record:
        return render_template(
            "login.html",
            error="This link has expired or has already been used. Request a new one.",
        )

    db.cleanup_expired_tokens()

    user = db.get_or_create_user(record["email"])

    payload = {
        "user_id": user["id"],
        "email": user["email"],
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24),
    }
    session_token = jwt.encode(payload, _jwt_secret(), algorithm="HS256")

    resp = make_response(redirect("/"))
    resp.set_cookie(
        _COOKIE_NAME,
        session_token,
        httponly=True,
        secure=True,
        samesite="Lax",
        path="/",
        max_age=_COOKIE_MAX_AGE,
    )
    return resp


@bp.route("/logout", methods=["GET", "POST"])
def logout():
    resp = make_response(redirect("/login"))
    resp.delete_cookie(_COOKIE_NAME, path="/")
    return resp


# ---------------------------------------------------------------------------
# Auth decorator
# ---------------------------------------------------------------------------


def require_auth(f):
    """
    Validates the JWT session cookie.
    Browser navigations without a valid session → redirect to /login.
    API calls without a valid session → 401 JSON.
    On success, attaches the DB user dict to request.current_user.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get(_COOKIE_NAME)
        if not token:
            return _auth_failure()
        try:
            payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return _auth_failure()
        except jwt.InvalidTokenError:
            return _auth_failure()

        user = db.get_user_by_id(payload.get("user_id"))
        if not user:
            return _auth_failure()

        request.current_user = user
        return f(*args, **kwargs)

    return decorated


def _auth_failure():
    is_browser_nav = (
        request.headers.get("Sec-Fetch-Mode") == "navigate"
        and request.headers.get("Sec-Fetch-Dest") == "document"
    )
    if is_browser_nav:
        return redirect("/login")
    return jsonify({"error": "Unauthorized"}), 401

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
# Email helpers
# ---------------------------------------------------------------------------

_BUTTON_STYLE = (
    "display:inline-block;padding:12px 24px;background:#000;color:#fff;"
    "text-decoration:none;font-family:Georgia,serif;font-size:14px;"
    "letter-spacing:0.05em;"
)


def _send_welcome_email(to_email, verify_url, expiry):
    html = f"""
<html><body style="background:#fff;color:#000;font-family:Georgia,serif;padding:40px 32px;max-width:560px;margin:0 auto;text-align:center;">

<p style="font-size:12px;line-height:1.7;margin:0 0 28px;">
Clear Seeing works best for people who are stuck. Not broken.
</p>

<p style="margin:0 0 28px;">
  <a href="{verify_url}" style="{_BUTTON_STYLE}">Enter Clear Seeing &rarr;</a>
</p>

<p style="font-size:10px;font-style:italic;line-height:1.6;color:#555;margin:0;">
By clicking this link you acknowledge this is a perception tool, not therapy, and not
appropriate for people in active mental health crisis. Use at own risk.<br>
If you are in crisis: 988 (Canada/US) &middot;
<a href="https://findahelpline.com" style="color:#555;">findahelpline.com</a>
</p>

<p style="font-size:10px;line-height:1.6;color:#888;margin:16px 0 0;font-family:Georgia,serif;">
New to Clear Seeing? Read the <a href="https://app.clearseeing.ca/user-manual" target="_blank" style="color:#888;">full guide</a> before your first session.
</p>

</body></html>
"""
    _post_email(to_email, "Your Clear Seeing login link", html)


def _send_login_email(to_email, verify_url, expiry):
    html = f"""
<html><body style="background:#000;color:#fff;font-family:Georgia,serif;padding:40px 32px;max-width:560px;">

<p style="margin:0 0 32px;">
  <a href="{verify_url}" style="{_BUTTON_STYLE}">Log in to Clear Seeing</a>
</p>

<p style="font-size:10px;color:#555;margin:0;">This link expires in {expiry} minutes.</p>

</body></html>
"""
    _post_email(to_email, "Your Clear Seeing login link", html)


def _post_email(to_email, subject, html):
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {_resend_key()}",
                "Content-Type": "application/json",
            },
            json={
                "from": _email_from(),
                "to": [to_email],
                "subject": subject,
                "html": html,
            },
            timeout=10,
        )
        if resp.status_code not in (200, 201):
            print(f"[magic_link] Resend error {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[magic_link] Email send failed: {e}")


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

    existing_user = db.get_user_by_email(email)
    if existing_user is None:
        _send_welcome_email(email, verify_url, expiry)
    else:
        _send_login_email(email, verify_url, expiry)

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

    is_new_user = db.get_user_by_email(record["email"]) is None
    user = db.get_or_create_user(record["email"])

    if is_new_user:
        db.acknowledge_disclaimer(user["id"])

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

"""
auth.py — thin wrapper for route-level auth enforcement.
Uses flask-login's current_user (set by replit_auth.py after OIDC login).
"""
from functools import wraps
from flask import request, jsonify, redirect, url_for, session
from flask_login import current_user


def require_auth(f):
    """
    Decorator for routes that require authentication.
    - Browser navigation requests (Sec-Fetch-Mode: navigate) are redirected
      to Replit login instead of receiving a 401.
    - XHR / fetch API calls receive a 401 JSON response so the frontend
      can handle it without a page redirect.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            is_browser_navigation = (
                request.headers.get("Sec-Fetch-Mode") == "navigate"
                and request.headers.get("Sec-Fetch-Dest") == "document"
            )
            if is_browser_navigation:
                session["next_url"] = request.url
                return redirect(url_for("replit_auth.login"))
            return jsonify({"error": "Unauthorized"}), 401
        request.current_user = current_user._user
        return f(*args, **kwargs)
    return decorated

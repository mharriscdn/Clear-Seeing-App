"""
auth.py — thin wrapper for route-level auth enforcement.
Uses flask-login's current_user (set by replit_auth.py after OIDC login).
"""
from functools import wraps
from flask import request, jsonify
from flask_login import current_user


def require_auth(f):
    """
    Decorator for API routes. Returns 401 JSON if not logged in.
    For page routes, use require_login from replit_auth.py instead
    (which does a redirect to the Replit login page).
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({"error": "Unauthorized"}), 401
        request.current_user = current_user._user
        return f(*args, **kwargs)
    return decorated

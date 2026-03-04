import os
import json
import urllib.request
from functools import wraps
from flask import request, jsonify, session
import db


def get_replit_user():
    """
    Reads the X-Replit-User-Id and X-Replit-User-Name headers injected by Replit Auth.
    Returns a dict with user info or None if not authenticated.
    """
    user_id = request.headers.get("X-Replit-User-Id")
    user_name = request.headers.get("X-Replit-User-Name")
    user_email = request.headers.get("X-Replit-User-Email")

    if not user_id or not user_name:
        return None

    # Use email if available, otherwise construct one from username
    email = user_email if user_email else f"{user_name}@replit.user"

    return {
        "replit_id": user_id,
        "username": user_name,
        "email": email,
    }


def require_auth(f):
    """Decorator that enforces Replit Auth on a route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        replit_user = get_replit_user()
        if not replit_user:
            return jsonify({"error": "Unauthorized"}), 401

        # Get or create user in our DB
        user = db.get_or_create_user(replit_user["email"])
        request.current_user = user
        return f(*args, **kwargs)

    return decorated

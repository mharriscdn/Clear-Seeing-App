"""
Replit Auth via OIDC (OpenID Connect) using flask-dance + flask-login.
Tokens are stored in Flask's server-side session (encrypted cookie) to
avoid pulling in SQLAlchemy alongside our existing psycopg2 setup.
"""
import jwt
import os
import uuid
from functools import wraps
from urllib.parse import urlencode

from flask import g, session, redirect, request, url_for
from flask_dance.consumer import (
    OAuth2ConsumerBlueprint,
    oauth_authorized,
    oauth_error,
)
from flask_dance.consumer.storage import BaseStorage
from flask_login import LoginManager, login_user, logout_user, current_user
from werkzeug.local import LocalProxy

import db

login_manager = LoginManager()


class SessionStorage(BaseStorage):
    """Store OAuth tokens in the Flask session (encrypted cookie). Simple and stateless."""

    def get(self, blueprint):
        return session.get(f"_oauth_token_{blueprint.name}")

    def set(self, blueprint, token):
        session[f"_oauth_token_{blueprint.name}"] = token
        session.modified = True

    def delete(self, blueprint):
        session.pop(f"_oauth_token_{blueprint.name}", None)


class ReplitUser:
    """Lightweight user object compatible with flask-login."""

    def __init__(self, user_record):
        self._user = user_record

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self._user["id"])

    def __getattr__(self, name):
        return self._user.get(name)


def make_replit_blueprint():
    repl_id = os.environ.get("REPL_ID")
    if not repl_id:
        raise SystemExit("REPL_ID environment variable must be set")

    issuer_url = os.environ.get("ISSUER_URL", "https://replit.com/oidc")

    replit_bp = OAuth2ConsumerBlueprint(
        "replit_auth",
        __name__,
        client_id=repl_id,
        client_secret=None,
        base_url=issuer_url,
        authorization_url_params={"prompt": "login consent"},
        token_url=issuer_url + "/token",
        token_url_params={"auth": (), "include_client_id": True},
        auto_refresh_url=issuer_url + "/token",
        auto_refresh_kwargs={"client_id": repl_id},
        authorization_url=issuer_url + "/auth",
        use_pkce=True,
        code_challenge_method="S256",
        scope=["openid", "profile", "email", "offline_access"],
        storage=SessionStorage(),
    )

    @replit_bp.before_app_request
    def set_applocal_session():
        if "_browser_session_key" not in session:
            session["_browser_session_key"] = uuid.uuid4().hex
        session.modified = True
        g.flask_dance_replit = replit_bp.session

    @replit_bp.route("/logout")
    def logout():
        del replit_bp.token
        logout_user()
        encoded_params = urlencode({
            "client_id": repl_id,
            "post_logout_redirect_uri": request.url_root,
        })
        logout_url = f"{issuer_url}/session/end?{encoded_params}"
        return redirect(logout_url)

    @replit_bp.route("/error")
    def error():
        return "Authentication error. Please try again.", 403

    return replit_bp


@oauth_authorized.connect
def logged_in(blueprint, token):
    """Called by flask-dance after the user completes OAuth."""
    claims = jwt.decode(token["id_token"], options={"verify_signature": False})
    email = claims.get("email") or f"{claims['sub']}@replit.user"
    user_record = db.get_or_create_user(email)
    user = ReplitUser(user_record)
    login_user(user)
    blueprint.token = token
    next_url = session.pop("next_url", None)
    if next_url:
        return redirect(next_url)


@oauth_error.connect
def handle_error(blueprint, error, error_description=None, error_uri=None):
    return redirect(url_for("replit_auth.error"))


def init_login_manager(app):
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        try:
            user_record = db.get_user_by_id(int(user_id))
        except (ValueError, Exception):
            return None
        if user_record:
            return ReplitUser(user_record)
        return None


def require_login(f):
    """Route decorator: redirects unauthenticated users to Replit login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            session["next_url"] = request.url
            return redirect(url_for("replit_auth.login"))
        return f(*args, **kwargs)
    return decorated_function


replit = LocalProxy(lambda: g.flask_dance_replit)

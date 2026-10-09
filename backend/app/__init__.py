import os
from datetime import timedelta
from flask import Flask, jsonify
from flask_login import LoginManager, current_user
from .models import db, User
from .routes_auth import bp_auth
from .routes_admin import bp_admin
from .routes_memberships import bp_mem
from .card_payment import bp_payment
from werkzeug.middleware.proxy_fix import ProxyFix
from .safe_logging import configure_logging, log_exception

def _env_bool(name, default):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")

def create_app():
    app = Flask(__name__)
    configure_logging(app)
    app.log_exception = lambda exc_info: log_exception("unhandled_request_error", exc_info)
    remember_days = int(os.getenv("REMEMBER_COOKIE_DAYS", "30"))
    database_url = os.getenv("DATABASE_URL", "").strip()
    secret_key = os.getenv("SECRET_KEY", "").strip()
    if not database_url or not secret_key:
        raise RuntimeError("DATABASE_URL and SECRET_KEY must be supplied in the environment")
    for prefix in ("postgresql://", "postgres://"):
        if database_url.startswith(prefix):
            database_url = "postgresql+psycopg://" + database_url[len(prefix):]
            break
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = secret_key
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "hide_parameters": True, "echo": False}
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = _env_bool("SESSION_COOKIE_SECURE", True)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["REMEMBER_COOKIE_DURATION"] = timedelta(days=remember_days)
    app.config["REMEMBER_COOKIE_SECURE"] = _env_bool(
        "REMEMBER_COOKIE_SECURE", app.config["SESSION_COOKIE_SECURE"]
    )
    app.config["REMEMBER_COOKIE_HTTPONLY"] = True
    app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
    app.config["MAIL_ADDRESS"] = os.getenv("MAIL_ADDRESS", "")
    app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD", "")
    app.config["MAIL_FROM_NAME"] = os.getenv("MAIL_FROM_NAME", "Commission Web FPMs")
    app.config["SMTP_HOST"] = os.getenv("SMTP_HOST", "smtp.gmail.com")
    app.config["SMTP_PORT"] = int(os.getenv("SMTP_PORT", "587"))
    app.config["SMTP_USE_TLS"] = os.getenv("SMTP_USE_TLS", "true")
    app.config["SMTP_USE_SSL"] = os.getenv("SMTP_USE_SSL", "false")
    app.config["FRONTEND_BASE_URL"] = os.getenv("FRONTEND_BASE_URL", "")
    app.config["PASSWORD_RESET_TOKEN_MAX_AGE"] = int(
        os.getenv("PASSWORD_RESET_TOKEN_MAX_AGE", "3600")
    )

    db.init_app(app)
    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.unauthorized_handler
    def unauthorized():
        # Make APIs return 401 JSON instead of flashing a page then redirecting
        return jsonify({"error": "unauthorized"}), 401

    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=int(os.getenv("PROXY_FIX_X_FOR", "1")),
        x_proto=int(os.getenv("PROXY_FIX_X_PROTO", "1")),
        x_host=int(os.getenv("PROXY_FIX_X_HOST", "1")),
        x_port=int(os.getenv("PROXY_FIX_X_PORT", "0")),
        x_prefix=int(os.getenv("PROXY_FIX_X_PREFIX", "0")),
    )

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(user_id)

    @app.get("/api/health")
    def health():
        return {"ok": True}

    app.register_blueprint(bp_auth)
    app.register_blueprint(bp_admin)
    app.register_blueprint(bp_mem)
    app.register_blueprint(bp_payment)

    # Auto-create tables only when explicitly enabled (avoid touching existing DBs)
    if os.getenv("AUTO_CREATE_DB", "").lower() in ("1", "true", "yes"):
        with app.app_context():
            try:
                db.create_all()
            except Exception:
                log_exception("auto_create_tables_failed")

    return app

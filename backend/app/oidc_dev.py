"""Experimental DEV-only OIDC RP; no identity adoption and no client-side tokens."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

import jwt
import requests
from cachelib.file import FileSystemCache
from flask import jsonify, redirect, request, session
from flask_login import current_user, login_user, logout_user
from flask_session import Session
from sqlalchemy.engine import make_url

from .models import db, Role, User


def bound_dev_uuid(subject, mapping):
    """Only explicit, verified bindings; issuer is checked before this lookup."""
    identity = mapping.get(subject)
    if not identity:
        raise ValueError("No verified business identity binding")
    return identity


def get_dev_user(subject, mapping):
    identity = bound_dev_uuid(subject, mapping)
    # No provisioning and no OIDC roles/groups: PostgreSQL owns business roles.
    return db.session.get(User, identity, populate_existing=True)


def verify_claims(encoded, key, issuer, audience, nonce, mapping, registration=False):
    claims = jwt.decode(encoded, key, algorithms=["RS256"], issuer=issuer,
        audience=audience, options={"require": ["iss", "sub", "aud", "exp", "iat", "nonce"]})
    if not isinstance(claims.get("nonce"), str) or not hmac.compare_digest(claims["nonce"], nonce):
        raise ValueError("OIDC nonce mismatch")
    if "azp" in claims and claims["azp"] != audience:
        raise ValueError("OIDC authorized party mismatch")
    if isinstance(claims["aud"], list) and len(claims["aud"]) > 1 and claims.get("azp") != audience:
        raise ValueError("OIDC authorized party required")
    if not registration and bound_dev_uuid(claims["sub"], mapping) != claims.get("carte_fede_uuid") and not (not claims.get("carte_fede_uuid") and getattr(mapping,"allows_empty_claim",lambda s:False)(claims["sub"])):
        raise ValueError("Authoritative identity binding mismatch")
    if claims.get("carte_fede_dev_allowed") is not True:
        raise ValueError("Active DEV identity required")
    return claims


def init_dev_oidc(app):
    app.config["DEV_OIDC"] = True
    uri = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
    if os.getenv("APP_ENV") != "development" or uri.database != "carte_fede_dev" or uri.username != "carte_fede_dev":
        raise RuntimeError("DEV OIDC requires its dedicated database and role")
    issuer = os.environ["OIDC_ISSUER_URL"]
    origin = "https://carte-dev.fede.fpms.ac.be"
    if issuer != "https://auth.fede.fpms.ac.be/application/o/carte-fede-dev/" or app.config["FRONTEND_BASE_URL"] != origin:
        raise RuntimeError("Unexpected DEV issuer or origin")
    client_id, client_secret = os.environ["OIDC_CLIENT_ID"], os.environ["OIDC_CLIENT_SECRET"]
    if client_id != "carte-fede-dev":
        raise RuntimeError("Unexpected DEV client")
    class IdentityMap(dict):
        def get(self, subject, default=None):
            value=super().get(subject)
            if value:return value
            from .dev_registration import bound_identity
            return bound_identity(subject) or default
        def allows_empty_claim(self, subject):
            from .dev_registration import identity_binding
            b=identity_binding(subject)
            return bool(b and b.state=='approved' and not b.managed)
    mapping = IdentityMap(json.loads(os.environ["OIDC_IDENTITY_BINDINGS"]))
    if not isinstance(mapping, dict) or not mapping:
        raise RuntimeError("Authoritative DEV bindings required")
    root = "https://auth.fede.fpms.ac.be"
    callback = origin + "/api/auth/oidc/callback"
    jwks = jwt.PyJWKClient(issuer + "jwks/", timeout=8)
    from .dev_session import configure_sessions, session_expired
    idle = int(os.getenv("DEV_SESSION_IDLE_SECONDS", "1800"))
    absolute = int(os.getenv("DEV_SESSION_ABSOLUTE_SECONDS", "28800"))
    if not 900 <= idle <= 7200 or not idle <= absolute <= 86400:
        raise RuntimeError("Invalid DEV session duration")
    password_url = os.getenv("OIDC_PASSWORD_CHANGE_URL", root + "/if/flow/default-password-change/")
    parsed_password = urlsplit(password_url)
    if parsed_password.scheme != "https" or parsed_password.netloc != "auth.fede.fpms.ac.be" or parsed_password.path != "/if/flow/default-password-change/" or parsed_password.query or parsed_password.fragment:
        raise RuntimeError("Unverified password change URL")
    app.config.update(DEV_SESSION_IDLE_SECONDS=idle, DEV_SESSION_ABSOLUTE_SECONDS=absolute)
    directory = "/tmp/carte-fede-dev-sessions"
    os.makedirs(directory, mode=0o700, exist_ok=True)
    app.config.update(SESSION_TYPE="cachelib", SESSION_CACHELIB=FileSystemCache(directory, threshold=500, mode=0o600),
        SESSION_COOKIE_NAME="__Host-carte-fede-dev", SESSION_PERMANENT=False,
        SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_DOMAIN=None, SESSION_COOKIE_PATH="/",
        PERMANENT_SESSION_LIFETIME=timedelta(seconds=absolute), SESSION_REFRESH_EACH_REQUEST=False, SESSION_USE_SIGNER=True)
    Session(app)
    configure_sessions(app, directory)

    def revoke_and_clear():
        tokens = [session.get("oidc_refresh_token"), session.get("oidc_access_token")]
        session.clear()
        logout_user()
        for token in filter(None, tokens):
            try:
                requests.post(root + "/application/o/revoke/", auth=(client_id, client_secret),
                    data={"token": token}, timeout=8, allow_redirects=False)
            except requests.RequestException:
                pass

    def validate_session():
        now = time.time()
        if session_expired(session, now, idle, absolute):
            raise ValueError("Session expired")
        if now >= session.get("oidc_expires_at", 0) - 20:
            refresh = session.get("oidc_refresh_token")
            if not refresh:
                raise ValueError("Refresh unavailable")
            r = requests.post(root + "/application/o/token/", auth=(client_id, client_secret),
                data={"grant_type": "refresh_token", "refresh_token": refresh}, timeout=8, allow_redirects=False)
            r.raise_for_status()
            token = r.json()
            if "id_token" in token:
                claims = jwt.decode(token["id_token"], jwks.get_signing_key_from_jwt(token["id_token"]).key,
                    algorithms=["RS256"], issuer=issuer, audience=client_id,
                    options={"require": ["iss", "sub", "aud", "exp", "iat"]})
                if claims.get("sub") != session.get("oidc_sub") or claims.get("carte_fede_dev_allowed") is not True or (claims.get("azp", client_id) != client_id) or ("nonce" in claims and not hmac.compare_digest(claims["nonce"], session.get("oidc_login_nonce", ""))):
                    raise ValueError("Invalid refreshed identity")
            ttl = int(token["expires_in"])
            if not 30 <= ttl <= 86400 or token.get("token_type", "").lower() != "bearer":
                raise ValueError("Invalid token response")
            session["oidc_access_token"] = token["access_token"]
            session["oidc_refresh_token"] = token.get("refresh_token", refresh)
            session["oidc_expires_at"] = now + ttl
        r = requests.get(root + "/application/o/userinfo/", headers={"Authorization": "Bearer " + session["oidc_access_token"]},
            timeout=8, allow_redirects=False)
        r.raise_for_status()
        info = r.json()
        bound = bound_dev_uuid(info.get("sub"), mapping)
        if info.get("sub") != session.get("oidc_sub") or info.get("carte_fede_dev_allowed") is not True or bound != str(current_user.id) or current_user.role == Role.ATTENTE or (bound != info.get("carte_fede_uuid") and not (not info.get("carte_fede_uuid") and mapping.allows_empty_claim(info.get("sub")))):
            raise ValueError("Identity no longer authorized")

    @app.before_request
    def dev_guard():
        if request.path == "/api/health":
            return None
        if request.path == "/api/auth/mode":
            return jsonify({"mode": "oidc", "development": True, "password_change_url": password_url})
        if request.path in {"/api/card-payment", "/api/card-payment/qr"}:
            if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("Origin") != origin:
                return jsonify({"error": "invalid_origin"}), 403
            return None
        if request.path in {"/api/auth/oidc/login", "/api/auth/oidc/callback", "/api/dev/registration", "/api/dev/enrollment-hook", "/api/dev/enrollment-confirm", "/api/dev/enrollment-notice"}:
            return None
        if request.path in {"/api/auth/login", "/api/auth/register"} or "password" in request.path.lower():
            return jsonify({"error": "local_auth_disabled_in_oidc_development"}), 403
        if not current_user.is_authenticated:
            if session.get("oidc_access_token"):
                revoke_and_clear()
            return jsonify({"error": "unauthorized"}), 401
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("Origin") != origin:
            return jsonify({"error": "invalid_origin"}), 403
        try:
            validate_session()
        except (ValueError, TypeError, KeyError, jwt.PyJWTError, requests.RequestException):
            revoke_and_clear()
            return jsonify({"error": "oidc_session_unavailable_or_revoked"}), 401
        if request.path in {"/api/verify", "/verify"} and current_user.role not in {Role.ADMIN, Role.VERIFIER}:
            return jsonify({"error": "forbidden"}), 403
        if request.path == "/api/auth/logout":
            revoke_and_clear()
            return jsonify({"ok": True})
        return None

    @app.get("/api/auth/oidc/login")
    def oidc_login():
        if current_user.is_authenticated and request.args.get("registration") != "1" and request.args.get("expired") != "1":
            try:
                validate_session()
                return redirect(origin + "/")
            except (ValueError, TypeError, KeyError, jwt.PyJWTError, requests.RequestException):
                revoke_and_clear()
        if session.get("oidc_access_token"):
            revoke_and_clear()
        session.clear()
        app.session_interface.regenerate(session)
        session["oidc_state"] = secrets.token_urlsafe(32)
        session["oidc_nonce"] = secrets.token_urlsafe(32)
        session["oidc_verifier"] = secrets.token_urlsafe(48)
        session["oidc_started"] = time.time()
        session["oidc_registration"] = request.args.get("registration") == "1" and os.getenv("DEV_REGISTRATION_ENABLED") == "1"
        next_path = request.args.get("next", "/")
        parsed = urlsplit(next_path)
        session["oidc_next"] = next_path if next_path.startswith("/") and not next_path.startswith("//") and not parsed.netloc and not parsed.scheme and "\\" not in next_path else "/"
        challenge = base64.urlsafe_b64encode(hashlib.sha256(session["oidc_verifier"].encode()).digest()).rstrip(b"=").decode()
        return redirect(root + "/application/o/authorize/?" + urlencode({"client_id": client_id,
            "redirect_uri": callback, "response_type": "code", "scope": "openid carte_fede_dev offline_access",
            "state": session["oidc_state"], "nonce": session["oidc_nonce"],
            "code_challenge": challenge, "code_challenge_method": "S256",
            **({"prompt": "login", "max_age": "0"} if request.args.get("expired") == "1" else {})}))

    @app.get("/api/auth/oidc/callback")
    def oidc_callback():
        state = session.pop("oidc_state", "")
        nonce = session.pop("oidc_nonce", "")
        verifier = session.pop("oidc_verifier", "")
        started = session.pop("oidc_started", 0)
        registration = session.pop("oidc_registration", False)
        target = session.pop("oidc_next", "/")
        try:
            if not state or not nonce or not verifier or time.time() - started > 300 or not hmac.compare_digest(state, request.args.get("state", "")) or not request.args.get("code") or "error" in request.args:
                raise ValueError("Invalid callback")
            r = requests.post(root + "/application/o/token/", auth=(client_id, client_secret),
                data={"grant_type": "authorization_code", "code": request.args["code"],
                    "redirect_uri": callback, "code_verifier": verifier}, timeout=8, allow_redirects=False)
            r.raise_for_status()
            token = r.json()
            from .dev_registration import automatic_accounts
            auto_accounts=automatic_accounts()
            claims = verify_claims(token["id_token"], jwks.get_signing_key_from_jwt(token["id_token"]).key,
                issuer, client_id, nonce, mapping, registration=registration or auto_accounts)
            if auto_accounts and not mapping.get(claims['sub']):
                # No privilege or identity adoption: native authenticated profile
                # intake followed by a fresh OIDC callback is still required.
                session.clear();app.session_interface.regenerate(session)
                return redirect(root+'/if/flow/carte-fede-dev-existing-registration/')
            if auto_accounts and not registration:
                verify_claims(token['id_token'],jwks.get_signing_key_from_jwt(token['id_token']).key,
                    issuer,client_id,nonce,mapping)
            if registration:
                session.clear()
                app.session_interface.regenerate(session)
                session.update(registration_subject=claims["sub"],registration_token=token["access_token"],registration_expires=min(claims["exp"],time.time()+300))
                return redirect(origin+"/register/?authenticated=1")
            user = get_dev_user(claims["sub"], mapping)
            if not user or user.role == Role.ATTENTE:
                raise ValueError("No authorized local identity")
            session.clear()
            login_user(user, remember=False, fresh=True)
            app.session_interface.regenerate(session)
            ttl = int(token["expires_in"])
            if not 30 <= ttl <= 86400 or token.get("token_type", "").lower() != "bearer" or not token.get("refresh_token"):
                raise ValueError("Renewable token required")
            session.update(oidc_sub=claims["sub"], oidc_access_token=token["access_token"],
                oidc_refresh_token=token["refresh_token"], oidc_login_nonce=nonce,
                oidc_expires_at=time.time()+ttl, oidc_created_at=time.time(), oidc_last_activity=time.time(),
                activity_csrf=secrets.token_urlsafe(32))
            return redirect(origin + "/")
        except (ValueError, TypeError, KeyError, jwt.PyJWTError, requests.RequestException):
            revoke_and_clear()
            return jsonify({"error": "oidc_authentication_rejected"}), 401

    @app.get("/api/auth/session")
    def session_status():
        return jsonify(idle_seconds=idle, absolute_seconds=absolute, server_now=time.time(),
            expires_at=min(session["oidc_last_activity"]+idle, session["oidc_created_at"]+absolute),
            activity_csrf=session["activity_csrf"])

    @app.post("/api/auth/session/activity")
    def session_activity():
        supplied=request.headers.get("X-Session-Activity-CSRF", "")
        if request.headers.get("Origin") != origin or not supplied or not hmac.compare_digest(supplied, session.get("activity_csrf", "")):
            return jsonify(error="invalid_activity_csrf"),403
        session["oidc_last_activity"]=time.time()
        return session_status()

    @app.after_request
    def no_oidc_caching(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

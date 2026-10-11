"""Experimental DEV-only OIDC RP; no identity adoption and no client-side tokens."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
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
from sqlalchemy.exc import IntegrityError


def bound_dev_uuid(subject, mapping):
    """Stable DEV-only pseudonym; never associate by editable attributes or email."""
    if subject in mapping:
        return mapping[subject]
    identity = uuid.UUID(subject)
    if str(identity) != subject:
        raise ValueError("Noncanonical subject")
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "carte-fede-dev/authentik/" + subject))


def get_dev_user(subject, mapping):
    identity = bound_dev_uuid(subject, mapping)
    user = db.session.get(User, identity)
    if user is None and subject not in mapping:
        user = User(id=identity, nom="DEV", prenom="Membre", member_id=None,
            email=identity + "@dev.invalid", password_hash="!disabled-local-auth", role=Role.MEMBER)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            user = db.session.get(User, identity)
            if user is None:
                raise
    # Existing-account DEV profiles never acquire elevated or imported roles.
    if subject not in mapping and user is not None and user.role != Role.MEMBER:
        raise ValueError("Existing-account DEV role must be MEMBER")
    return user


def verify_claims(encoded, key, issuer, audience, nonce, mapping):
    claims = jwt.decode(encoded, key, algorithms=["RS256"], issuer=issuer,
        audience=audience, options={"require": ["iss", "sub", "aud", "exp", "iat", "nonce"]})
    if not isinstance(claims.get("nonce"), str) or not hmac.compare_digest(claims["nonce"], nonce):
        raise ValueError("OIDC nonce mismatch")
    if "azp" in claims and claims["azp"] != audience:
        raise ValueError("OIDC authorized party mismatch")
    if isinstance(claims["aud"], list) and len(claims["aud"]) > 1 and claims.get("azp") != audience:
        raise ValueError("OIDC authorized party required")
    if bound_dev_uuid(claims["sub"], mapping) != claims.get("carte_fede_uuid"):
        raise ValueError("Authoritative identity binding mismatch")
    if claims.get("carte_fede_dev_allowed") is not True:
        raise ValueError("Active DEV identity required")
    return claims


def init_dev_oidc(app):
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
    mapping = json.loads(os.environ["OIDC_IDENTITY_BINDINGS"])
    if not isinstance(mapping, dict) or not mapping:
        raise RuntimeError("Authoritative DEV bindings required")
    root = "https://auth.fede.fpms.ac.be"
    callback = origin + "/api/auth/oidc/callback"
    jwks = jwt.PyJWKClient(issuer + "jwks/", timeout=8)
    directory = "/tmp/carte-fede-dev-sessions"
    os.makedirs(directory, mode=0o700, exist_ok=True)
    app.config.update(SESSION_TYPE="cachelib", SESSION_CACHELIB=FileSystemCache(directory, threshold=500, mode=0o600),
        SESSION_COOKIE_NAME="__Host-carte-fede-dev", SESSION_PERMANENT=False,
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=5), SESSION_USE_SIGNER=True)
    Session(app)

    def revoke_and_clear():
        token = session.get("oidc_access_token")
        session.clear()
        logout_user()
        if token:
            try:
                requests.post(root + "/application/o/revoke/", auth=(client_id, client_secret),
                    data={"token": token}, timeout=8, allow_redirects=False)
            except requests.RequestException:
                pass

    @app.before_request
    def dev_guard():
        if request.path == "/api/health":
            return None
        if request.path == "/api/auth/mode":
            return jsonify({"mode": "oidc", "development": True})
        if request.path in {"/api/auth/oidc/login", "/api/auth/oidc/callback"}:
            return None
        if request.path.startswith(("/api/card-payment", "/api/admin/card-payment")):
            return jsonify({"error": "payments_disabled_in_development"}), 403
        if request.path in {"/api/auth/login", "/api/auth/register"} or "password" in request.path.lower():
            return jsonify({"error": "local_auth_disabled_in_oidc_development"}), 403
        if not current_user.is_authenticated:
            return jsonify({"error": "unauthorized"}), 401
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("Origin") != origin:
            return jsonify({"error": "invalid_origin"}), 403
        try:
            if time.time() >= session.get("oidc_expires_at", 0):
                raise ValueError("Session expired")
            r = requests.get(root + "/application/o/userinfo/", headers={"Authorization": "Bearer " + session["oidc_access_token"]},
                timeout=8, allow_redirects=False)
            r.raise_for_status()
            info = r.json()
            if info.get("sub") != session.get("oidc_sub") or info.get("carte_fede_dev_allowed") is not True or bound_dev_uuid(info.get("sub"), mapping) != info.get("carte_fede_uuid") or str(current_user.id) != info.get("carte_fede_uuid") or current_user.role == Role.ATTENTE:
                raise ValueError("Identity no longer authorized")
        except (ValueError, KeyError, requests.RequestException):
            revoke_and_clear()
            return jsonify({"error": "oidc_session_unavailable_or_revoked"}), 401
        if request.path == "/api/auth/logout":
            revoke_and_clear()
            return jsonify({"ok": True})
        return None

    @app.get("/api/auth/oidc/login")
    def oidc_login():
        session.clear()
        app.session_interface.regenerate(session)
        session["oidc_state"] = secrets.token_urlsafe(32)
        session["oidc_nonce"] = secrets.token_urlsafe(32)
        session["oidc_verifier"] = secrets.token_urlsafe(48)
        session["oidc_started"] = time.time()
        next_path = request.args.get("next", "/")
        parsed = urlsplit(next_path)
        session["oidc_next"] = next_path if next_path.startswith("/") and not next_path.startswith("//") and not parsed.netloc and not parsed.scheme and "\\" not in next_path else "/"
        challenge = base64.urlsafe_b64encode(hashlib.sha256(session["oidc_verifier"].encode()).digest()).rstrip(b"=").decode()
        return redirect(root + "/application/o/authorize/?" + urlencode({"client_id": client_id,
            "redirect_uri": callback, "response_type": "code", "scope": "openid carte_fede_dev",
            "state": session["oidc_state"], "nonce": session["oidc_nonce"],
            "code_challenge": challenge, "code_challenge_method": "S256"}))

    @app.get("/api/auth/oidc/callback")
    def oidc_callback():
        state = session.pop("oidc_state", "")
        nonce = session.pop("oidc_nonce", "")
        verifier = session.pop("oidc_verifier", "")
        started = session.pop("oidc_started", 0)
        target = session.pop("oidc_next", "/")
        try:
            if not state or not nonce or not verifier or time.time() - started > 300 or not hmac.compare_digest(state, request.args.get("state", "")) or not request.args.get("code") or "error" in request.args:
                raise ValueError("Invalid callback")
            r = requests.post(root + "/application/o/token/", auth=(client_id, client_secret),
                data={"grant_type": "authorization_code", "code": request.args["code"],
                    "redirect_uri": callback, "code_verifier": verifier}, timeout=8, allow_redirects=False)
            r.raise_for_status()
            token = r.json()
            claims = verify_claims(token["id_token"], jwks.get_signing_key_from_jwt(token["id_token"]).key,
                issuer, client_id, nonce, mapping)
            user = get_dev_user(claims["sub"], mapping)
            if not user or user.role == Role.ATTENTE:
                raise ValueError("No authorized local identity")
            session.clear()
            login_user(user, remember=False, fresh=True)
            app.session_interface.regenerate(session)
            session.update(oidc_sub=claims["sub"], oidc_access_token=token["access_token"],
                oidc_expires_at=min(claims["exp"], time.time() + 300))
            return redirect(target)
        except (ValueError, KeyError, jwt.PyJWTError, requests.RequestException):
            revoke_and_clear()
            return jsonify({"error": "oidc_authentication_rejected"}), 401

    @app.after_request
    def no_oidc_caching(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

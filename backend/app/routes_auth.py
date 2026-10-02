from flask import Blueprint, request, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from .models import db, User, Role, PendingRegistration
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import BadSignature, SignatureExpired
from .email_utils import send_email
from .password_reset import generate_reset_token, verify_reset_token
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta
import re


bp_auth = Blueprint("auth", __name__)

@bp_auth.route("/api/auth/login", methods=["POST"])
def login():
    try:
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        password = (data.get("password") or "")
        remember = bool(data.get("remember", True))

        user = None
        if email:
            user = User.query.filter_by(email=email).first()
        else:
            ident = (data.get("identifiant") or "").strip()
            if ident and ident.isdigit() and len(ident) == 6:
                user = User.query.filter_by(member_id=ident).first()

        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({"error": "Invalid credentials"}), 401

        login_user(user, remember=remember)
        role_value = getattr(user.role, "value", user.role)
        return jsonify({"ok": True, "user": {
            "email": user.email or "",
            "member_id": user.member_id or "",
            "role": role_value
        }})
    except Exception:
        current_app.logger.exception("Login error")
        return jsonify({"error": "Server error"}), 500

@bp_auth.route("/api/auth/logout", methods=["POST"])
@login_required
def logout():
    print("Logout user:", current_user)
    logout_user()
    return jsonify({"ok": True})


@bp_auth.route("/api/me", methods=["GET"])
@login_required
def me():
    user = current_user
    role_value = getattr(user.role, "value", user.role)
    identifiant = user.member_id or user.email  
    return jsonify({
        "member_id": user.member_id or "",  
        "email": user.email or "",
        "role": role_value,
        "identifiant": identifiant  
    })


@bp_auth.route("/api/auth/register", methods=["POST"])
def register():
    try:
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict) or not all(isinstance(data.get(field), str) for field in ("nom", "prenom", "member_id", "password", "password2")):
            return jsonify({"error": "Champs d'inscription invalides."}), 400
        password = data["password"]
        nom = data["nom"].strip()
        prenom = data["prenom"].strip()
        member_id = data["member_id"].strip()
        if not nom or not prenom or not re.fullmatch(r"[0-9]{6}", member_id):
            return jsonify({"error": "Nom, prénom et matricule à 6 chiffres requis."}), 400
        if len(nom) > 100 or len(prenom) > 100 or not 8 <= len(password) <= 128:
            return jsonify({"error": "Nom/prénom trop long ou mot de passe hors limite (8 à 128 caractères)."}), 400
        if password != data.get("password2"):
            return jsonify({"error": "Les mots de passe ne correspondent pas."}), 400
        if User.query.filter_by(member_id=member_id).first():
            return jsonify({"error": "Un compte existe déjà avec ce matricule."}), 409

        # Expired rows are discarded on access; no background scheduler is needed.
        PendingRegistration.query.filter(PendingRegistration.expires_at <= datetime.utcnow()).delete()
        if PendingRegistration.query.filter_by(member_id=member_id).first():
            db.session.rollback()
            return jsonify({"error": "Une inscription est déjà en attente pour ce matricule."}), 409
        pending = PendingRegistration(
            member_id=member_id,
            nom=nom,
            prenom=prenom,
            password_hash=generate_password_hash(password),
            expires_at=datetime.utcnow() + timedelta(days=30),
        )
        db.session.add(pending)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"error": "Une inscription est déjà en attente pour ce matricule."}), 409
        return jsonify({"ok": True, "expires_at": pending.expires_at.isoformat()}), 202
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Register error")
        return jsonify({"error": "Inscription indisponible. Réessayez plus tard."}), 500


@bp_auth.route("/api/auth/change-password", methods=["POST"])
@login_required
def change_password():
    data = request.json or {}
    old_password = data.get("old_password", "").strip()
    new_password = data.get("new_password", "").strip()

    if not old_password or not new_password or len(new_password) < 8:
        return jsonify({"error": "Champs invalides ou mot de passe trop court"}), 400

    # Vérifier l'ancien mot de passe
    if not check_password_hash(current_user.password_hash, old_password):
        return jsonify({"error": "Ancien mot de passe incorrect"}), 403

    # Mettre à jour le mot de passe
    current_user.password_hash = generate_password_hash(new_password)
    db.session.commit()

    return jsonify({"ok": True})


@bp_auth.route("/api/auth/request-password-reset", methods=["POST"])
def request_password_reset():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    ident = (data.get("identifiant") or "").strip()
    if not email and not ident:
        return jsonify({"ok": True})

    user = User.query.filter_by(email=email).first()
    if not user and ident and ident.isdigit() and len(ident) == 6:
        user = User.query.filter_by(member_id=ident).first()
    if not user:
        return jsonify({"ok": True})

    token = generate_reset_token(user)
    base_url = (current_app.config.get("FRONTEND_BASE_URL") or "").strip()
    if not base_url:
        base_url = request.host_url.rstrip("/")
    reset_url = f"{base_url}/ResetPassword?token={token}"
    max_age = int(current_app.config.get("PASSWORD_RESET_TOKEN_MAX_AGE", 3600))
    minutes = max(1, int(max_age / 60))

    body = (
        f"Bonjour {user.prenom or ''},\n\n"
        "Une demande de reinitialisation de mot de passe a ete faite pour votre compte.\n"
        f"Pour choisir un nouveau mot de passe, cliquez sur ce lien (valable {minutes} min):\n"
        f"{reset_url}\n\n"
        "Si vous n'etes pas a l'origine de cette demande, ignorez cet email."
    )

    recipient = user.email or (
        f"{user.member_id}@umons.ac.be" if user.member_id else None
    )
    if not recipient:
        return jsonify({"ok": True})

    try:
        send_email(recipient, "Reinitialisation de mot de passe", body)
    except Exception:
        current_app.logger.exception("Password reset email failed")

    return jsonify({"ok": True})


@bp_auth.route("/api/auth/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    new_password = (data.get("new_password") or "").strip()

    if not token or not new_password or len(new_password) < 8:
        return jsonify({"error": "Champs invalides ou mot de passe trop court"}), 400

    try:
        payload = verify_reset_token(
            token, int(current_app.config.get("PASSWORD_RESET_TOKEN_MAX_AGE", 3600))
        )
    except SignatureExpired:
        return jsonify({"error": "Lien expiré"}), 400
    except BadSignature:
        return jsonify({"error": "Lien invalide"}), 400

    user_id = payload.get("uid")
    password_hash = payload.get("ph")
    user = User.query.get(user_id) if user_id else None
    if not user or user.password_hash != password_hash:
        return jsonify({"error": "Lien invalide"}), 400

    user.password_hash = generate_password_hash(new_password)
    db.session.commit()

    return jsonify({"ok": True})

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from .models import db, User, Role, PendingRegistration
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import BadSignature, SignatureExpired
from .email_utils import send_email
from .safe_logging import log_exception
from .password_reset import generate_reset_token, verify_reset_token
from .routes_memberships import current_academic_year
from sqlalchemy import func
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
        log_exception("login_failed")
        return jsonify({"error": "Server error"}), 500

@bp_auth.route("/api/auth/logout", methods=["POST"])
@login_required
def logout():
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
        "identifiant": identifiant,
        "nom": user.nom,
        "prenom": user.prenom,
    })


@bp_auth.route("/api/auth/register", methods=["POST"])
def register():
    try:
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict) or not all(isinstance(data.get(field), str) for field in ("nom", "prenom", "password", "password2")) or not all(isinstance(data.get(field, ""), str) for field in ("member_id", "email")):
            return jsonify({"error": "Champs d'inscription invalides."}), 400
        password = data["password"]
        nom = data["nom"].strip()
        prenom = data["prenom"].strip()
        member_id = data.get("member_id", "").strip()
        email = data.get("email", "").strip().lower()
        if not nom or not prenom or bool(member_id) == bool(email):
            return jsonify({"error": "Nom, prénom et un seul identifiant (matricule ou email) requis."}), 400
        if member_id and not re.fullmatch(r"[0-9]{6}", member_id):
            return jsonify({"error": "Le matricule doit contenir 6 chiffres."}), 400
        if email and (len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)):
            return jsonify({"error": "Adresse email invalide."}), 400
        if len(nom) > 100 or len(prenom) > 100 or not 8 <= len(password) <= 128:
            return jsonify({"error": "Nom/prénom trop long ou mot de passe hors limite (8 à 128 caractères)."}), 400
        if password != data.get("password2"):
            return jsonify({"error": "Les mots de passe ne correspondent pas."}), 400
        if type(data.get("free_card_requested", False)) is not bool:
            return jsonify({"error": "Option de carte gratuite invalide."}), 400
        if (member_id and User.query.filter_by(member_id=member_id).first()) or (
            email and User.query.filter(func.lower(User.email) == email).first()
        ):
            return jsonify({"error": "Un compte existe déjà avec cet identifiant."}), 409

        # Expired rows are discarded on access; no background scheduler is needed.
        PendingRegistration.query.filter(PendingRegistration.expires_at <= datetime.utcnow()).delete()
        if (member_id and PendingRegistration.query.filter_by(member_id=member_id).first()) or (
            email and PendingRegistration.query.filter(func.lower(PendingRegistration.email) == email).first()
        ):
            db.session.rollback()
            return jsonify({"error": "Une inscription est déjà en attente pour cet identifiant."}), 409
        pending = PendingRegistration(
            member_id=member_id or None,
            email=email or None,
            nom=nom,
            prenom=prenom,
            password_hash=generate_password_hash(password),
            expires_at=datetime.utcnow() + timedelta(days=30),
            free_card_requested=data.get("free_card_requested") is True,
            card_year=current_academic_year(),
        )
        db.session.add(pending)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"error": "Une inscription est déjà en attente pour cet identifiant."}), 409
        return jsonify({"ok": True, "expires_at": pending.expires_at.isoformat(), "card_year": pending.card_year}), 202
    except Exception:
        db.session.rollback()
        log_exception("register_failed")
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
        log_exception("password_reset_email_failed")

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

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from sqlalchemy.orm import joinedload
from .models import db, User, Role, Membership, PendingRegistration, PendingCardRequest, Room, VoteSession, VoteOption, VoteBallot
from .routes_memberships import next_available_card_code, ALLOWED_PREFIXES, current_academic_year
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta
import re

bp_admin = Blueprint("admin", __name__)

@bp_admin.before_request
@login_required
def _require_admin():
    # Si pas admin -> 403. Si pas loggé -> 401 via unauthorized_handler ci-dessus
    if not (current_user.is_authenticated and current_user.role == Role.ADMIN):
        return jsonify({"error": "Forbidden"}), 403

def is_admin():
    return current_user.is_authenticated and current_user.role == Role.ADMIN

def _room_to_dict(room: Room):
    return {
        "id": room.id,
        "title": room.title,
        "code": room.code,
        "password": room.password,
        "created_at": room.created_at.isoformat() if room.created_at else None,
        "expires_at": room.expires_at.isoformat() if room.expires_at else None,
        "created_by": room.created_by,
    }

def _session_to_dict(session: VoteSession):
    return {
        "id": session.id,
        "room_id": session.room_id,
        "question": session.question,
        "status": session.status,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "closed_at": session.closed_at.isoformat() if session.closed_at else None,
        "options": [{"id": o.id, "text": o.text} for o in (session.options or [])],
    }

@bp_admin.get("/api/admin/requests")
def pending_requests():
    now = datetime.utcnow()
    PendingRegistration.query.filter(PendingRegistration.expires_at <= now).delete()
    db.session.commit()
    registrations = PendingRegistration.query.order_by(PendingRegistration.created_at.asc()).all()
    cards = PendingCardRequest.query.filter_by(status="pending").order_by(PendingCardRequest.created_at.asc()).all()
    return jsonify({
        "registrations": [{"id": row.id, "nom": row.nom, "prenom": row.prenom,
                           "member_id": row.member_id, "created_at": row.created_at.isoformat(),
                           "expires_at": row.expires_at.isoformat()} for row in registrations],
        "cards": [{"id": row.id, "annee": row.annee, "nom": row.user.nom,
                   "prenom": row.user.prenom, "identifiant": row.user.member_id or row.user.email,
                   "created_at": row.created_at.isoformat()} for row in cards],
    })


@bp_admin.post("/api/admin/registrations/<request_id>/<decision>")
def decide_registration(request_id, decision):
    if decision not in ("approve", "reject"):
        return jsonify({"error": "Décision invalide."}), 404
    row = PendingRegistration.query.filter_by(id=request_id).first()
    if not row or row.expires_at <= datetime.utcnow():
        return jsonify({"error": "Demande expirée ou introuvable."}), 404
    if decision == "reject":
        db.session.delete(row)
        db.session.commit()
        return jsonify({"ok": True})
    if User.query.filter_by(member_id=row.member_id).first():
        return jsonify({"error": "Un compte existe déjà avec ce matricule."}), 409
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Données invalides."}), 400
    add_card = data.get("add_card") is True
    year = data.get("annee")
    prefix = str(data.get("prefix") or "A").upper()
    if add_card and (type(year) is not int or year not in (current_academic_year(), current_academic_year() + 1) or prefix not in ALLOWED_PREFIXES):
        return jsonify({"error": "Année ou préfixe de carte invalide."}), 400
    user = User(nom=row.nom, prenom=row.prenom, member_id=row.member_id,
                password_hash=row.password_hash, role=Role.MEMBER)
    try:
        db.session.add(user)
        db.session.flush()
        if add_card:
            db.session.add(Membership(user_id=user.id, annee=year,
                                      annee_code=next_available_card_code(year, prefix)))
        db.session.delete(row)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Conflit de matricule ou de numéro de carte. Réessayez."}), 409
    return jsonify({"ok": True, "user_id": user.id})


@bp_admin.post("/api/admin/card-requests/<request_id>/<decision>")
def decide_card_request(request_id, decision):
    if decision not in ("approve", "reject"):
        return jsonify({"error": "Décision invalide."}), 404
    row = PendingCardRequest.query.filter_by(id=request_id, status="pending").first()
    if not row:
        return jsonify({"error": "Demande introuvable."}), 404
    if decision == "reject":
        row.status = "rejected"
        db.session.commit()
        return jsonify({"ok": True})
    if Membership.query.filter_by(user_id=row.user_id, annee=row.annee).first():
        return jsonify({"error": "Ce compte possède déjà une carte pour cette année."}), 409
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Données invalides."}), 400
    prefix = str(data.get("prefix") or "A").upper()
    if prefix not in ALLOWED_PREFIXES:
        return jsonify({"error": "Préfixe invalide."}), 400
    try:
        db.session.add(Membership(user_id=row.user_id, annee=row.annee,
                                  annee_code=next_available_card_code(row.annee, prefix)))
        db.session.delete(row)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Conflit de numéro de carte. Réessayez."}), 409
    return jsonify({"ok": True})

@bp_admin.route("/api/admin/users", methods=["GET", "POST"])
@login_required
def users_collection():
    if request.method == "POST":
        data = request.json or {}
        nom = (data.get("nom") or "").strip()
        prenom = (data.get("prenom") or "").strip()
        email = (data.get("email") or "").strip().lower() or None
        member_id = (data.get("member_id") or "").strip() or None
        password = (data.get("password") or "").strip()

        if not nom or not prenom or not password:
            return jsonify({"error": "Champs requis: nom, prenom, password + (member_id OU email)"}), 400
        if not member_id and not email:
            return jsonify({"error": "Fournir soit member_id (6 chiffres) soit email"}), 400
        if member_id and (len(member_id) != 6 or not member_id.isdigit()):
            return jsonify({"error": "member_id doit être 6 chiffres"}), 400
        if member_id and User.query.filter_by(member_id=member_id).first():
            return jsonify({"error": "member_id déjà utilisé"}), 409
        if email and User.query.filter_by(email=email).first():
            return jsonify({"error": "email déjà utilisé"}), 409

        role_str = (data.get("role") or "member").lower()
        allowed = {"member": Role.MEMBER, "admin": Role.ADMIN, "verifier": Role.VERIFIER, "en attente":Role.ATTENTE}
        if role_str not in allowed:
            return jsonify({"error": "Rôle invalide"}), 400
        role = allowed[role_str]


        user = User(
            nom=nom,
            prenom=prenom,
            email=email,
            member_id=member_id,
            password_hash=generate_password_hash(password),
            role=role,
        )
        db.session.add(user)
        db.session.flush()

        cartes = data.get("cartes", [])
        for c in cartes:
            annee = c.get("annee")
            annee_code = c.get("annee_code")
            if annee and annee_code:
                m = Membership(user_id=user.id, annee=annee, annee_code=annee_code)
                db.session.add(m)

        db.session.commit()
        return jsonify({"ok": True, "id": user.id})

    # GET: lister avec dictionnaire {annee: code} + rôle
    users = (
        User.query
        .options(joinedload(User.memberships))
        .order_by(User.nom.asc(), User.prenom.asc())
        .all()
    )
    result = []
    for u in users:
        cartes = {str(m.annee): m.annee_code for m in (u.memberships or [])}
        result.append({
            "id": u.id,
            "nom": u.nom,
            "prenom": u.prenom,
            "identifiant": (u.member_id or u.email),
            "role": (u.role.value if hasattr(u.role, "value") else str(u.role)), 
            "cartes": cartes,
        })
    return jsonify(result)

@bp_admin.route("/api/admin/users/<user_id>/role", methods=["PUT"])
@login_required
def set_user_role(user_id):
    """Changer le rôle d'un utilisateur (admin only)."""
    if not is_admin():
        return jsonify({"error": "Forbidden"}), 403

    target = User.query.get(user_id)
    if not target:
        return jsonify({"error": "User introuvable"}), 404

    data = request.get_json() or {}
    role_str = str(data.get("role", "")).lower().strip()
    allowed = {"member": Role.MEMBER, "admin": Role.ADMIN, "verifier": Role.VERIFIER, "en attente": Role.ATTENTE}
    if role_str not in allowed:
        return jsonify({"error": "Rôle invalide"}), 400

    # (optionnel) éviter que l'admin courant se rétrograde par accident
    if target.id == current_user.id and role_str != "admin":
        return jsonify({"error": "Impossible de rétrograder votre propre compte."}), 400

    target.role = allowed[role_str]
    db.session.commit()
    return jsonify({"ok": True, "id": target.id, "role": role_str})

@bp_admin.route("/api/admin/users/<user_id>", methods=["PUT"])
@login_required
def update_user(user_id):
    if not is_admin():
        return jsonify({"error": "Forbidden"}), 403

    target = User.query.get(user_id)
    if not target:
        return jsonify({"error": "Utilisateur introuvable"}), 404

    data = request.get_json()
    nom = data.get("nom")
    prenom = data.get("prenom")
    identifiant = data.get("identifiant")  # ⚡ ajout

    if identifiant and not re.match(r"^\d{6}$", identifiant):
        return jsonify({"error": "Le member_id doit faire 6 chiffres"}), 400

    if nom:
        target.nom = nom
    if prenom:
        target.prenom = prenom
    if identifiant:
        target.member_id = identifiant  # ⚡ mise à jour du member_id

    db.session.commit()
    return jsonify({"ok": True})

@bp_admin.route("/api/admin/users/<user_id>", methods=["DELETE"])
@login_required
def delete_user(user_id):
    if not is_admin():
        return jsonify({"error": "Forbidden"}), 403

    target = User.query.get(user_id)
    if not target:
        return jsonify({"error": "Utilisateur introuvable"}), 404

    # ⚠️ Sécurité : éviter qu’un admin se supprime lui-même
    if target.id == current_user.id:
        return jsonify({"error": "Impossible de supprimer votre propre compte."}), 400

    db.session.delete(target)
    db.session.commit()
    return jsonify({"ok": True})

@bp_admin.route("/api/admin/next_num", methods=["GET"])
@login_required
def get_next_card_number():
    """Retourne le prochain numéro disponible pour une année et un préfixe."""
    if not is_admin():
        return jsonify({"error": "Forbidden"}), 403

    annee = request.args.get("annee")
    prefix = request.args.get("prefix")

    if not annee or not prefix:
        return jsonify({"error": "annee et prefix requis"}), 400

    # Trouver tous les annee_code existants pour cette année et ce préfixe
    like_pattern = f"{prefix}-%"
    existing = Membership.query.filter(
        Membership.annee == int(annee.split("-")[0]),
        Membership.annee_code.ilike(like_pattern)
    ).all()

    nums = []
    for m in existing:
        try:
            n = int(m.annee_code.split("-")[1])
            nums.append(n)
        except:
            pass

    next_num = max(nums) + 1 if nums else 1
    return jsonify({"next_num": next_num})

# ---------------- Rooms (admin) ----------------
@bp_admin.route("/api/admin/rooms", methods=["GET", "POST"])
@login_required
def admin_rooms_collection():
    if request.method == "POST":
        data = request.get_json() or {}
        title = str(data.get("title") or "").strip()
        duration = data.get("duration_minutes") or 30
        password = str(data.get("password") or "").strip() or None

        if not title:
            return jsonify({"error": "Titre requis"}), 400

        try:
            duration = int(duration)
        except Exception:
            return jsonify({"error": "Durée invalide"}), 400
        if duration <= 0 or duration > 24 * 60:
            return jsonify({"error": "Durée invalide"}), 400

        # Générer code unique
        code = None
        for _ in range(10):
            candidate = Room.generate_code(6)
            if not Room.query.filter_by(code=candidate).first():
                code = candidate
                break
        if not code:
            return jsonify({"error": "Impossible de générer un code"}), 500

        if not password:
            password = Room.generate_password(10)

        now = datetime.utcnow()
        room = Room(
            title=title,
            code=code,
            password=password,
            created_at=now,
            expires_at=now + timedelta(minutes=duration),
            created_by=current_user.id,
        )
        db.session.add(room)
        db.session.commit()
        return jsonify(_room_to_dict(room)), 201

    rooms = Room.query.order_by(Room.created_at.desc()).all()
    return jsonify([_room_to_dict(r) for r in rooms])

@bp_admin.route("/api/admin/rooms/<room_id>", methods=["DELETE"])
@login_required
def admin_delete_room(room_id):
    room = Room.query.get(room_id)
    if not room:
        return jsonify({"error": "Room introuvable"}), 404
    db.session.delete(room)
    db.session.commit()
    return jsonify({"ok": True})

@bp_admin.route("/api/admin/rooms/<room_id>/extend", methods=["PUT"])
@login_required
def admin_extend_room(room_id):
    data = request.get_json() or {}
    minutes = data.get("minutes")
    try:
        minutes = int(minutes)
    except Exception:
        return jsonify({"error": "minutes invalide"}), 400
    if minutes <= 0 or minutes > 24 * 60:
        return jsonify({"error": "minutes invalide"}), 400

    room = Room.query.get(room_id)
    if not room:
        return jsonify({"error": "Room introuvable"}), 404

    if room.expires_at is None:
        room.expires_at = datetime.utcnow() + timedelta(minutes=minutes)
    else:
        room.expires_at = room.expires_at + timedelta(minutes=minutes)
    db.session.commit()
    return jsonify(_room_to_dict(room))

@bp_admin.route("/api/admin/rooms/<room_id>/vote", methods=["POST"])
@login_required
def admin_create_vote(room_id):
    data = request.get_json() or {}
    question = str(data.get("question") or "").strip()
    options = data.get("options") or []

    if not question:
        return jsonify({"error": "Question requise"}), 400
    if not isinstance(options, list):
        return jsonify({"error": "Options invalides"}), 400

    clean_options = [str(o).strip() for o in options if str(o).strip()]
    if len(clean_options) < 2:
        return jsonify({"error": "Au moins 2 options requises"}), 400

    room = Room.query.get(room_id)
    if not room:
        return jsonify({"error": "Room introuvable"}), 404

    # Close existing open session
    open_session = VoteSession.query.filter_by(room_id=room_id, status="open").first()
    if open_session:
        open_session.status = "closed"
        open_session.closed_at = datetime.utcnow()

    session = VoteSession(room_id=room_id, question=question, status="open")
    db.session.add(session)
    db.session.flush()

    for text in clean_options:
        db.session.add(VoteOption(session_id=session.id, text=text))

    db.session.commit()
    return jsonify(_session_to_dict(session)), 201

@bp_admin.route("/api/admin/rooms/<room_id>/vote/<session_id>/close", methods=["PUT"])
@login_required
def admin_close_vote(room_id, session_id):
    session = VoteSession.query.filter_by(id=session_id, room_id=room_id).first()
    if not session:
        return jsonify({"error": "Vote introuvable"}), 404
    if session.status != "closed":
        session.status = "closed"
        session.closed_at = datetime.utcnow()
        db.session.commit()
    return jsonify(_session_to_dict(session))

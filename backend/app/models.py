from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from enum import Enum
from sqlalchemy.orm import relationship
import uuid
import secrets

db = SQLAlchemy()

class Role(Enum):
    MEMBER = "member"
    ADMIN  = "admin"
    VERIFIER = "verifier"
    ATTENTE = "en attente"
    

class User(UserMixin, db.Model):
    __tablename__ = "user"
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    nom = db.Column(db.String, nullable=False)
    prenom = db.Column(db.String, nullable=False)

    # Identifiant au choix : id 6 chiffres OU email (au moins l'un des deux)
    member_id = db.Column(db.String(6), unique=True, nullable=True)  # 6 chiffres
    email = db.Column(db.String, unique=True, nullable=True)

    password_hash = db.Column(db.String, nullable=False)
    role = db.Column(db.Enum(Role, name="role_enum"), default=Role.MEMBER, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    memberships = relationship("Membership", backref="user", cascade="all, delete-orphan")

    __table_args__ = (
        db.CheckConstraint("(member_id IS NOT NULL) OR (email IS NOT NULL)", name="user_id_or_email_required"),
        db.CheckConstraint("(member_id ~ '^[0-9]{6}$') OR (member_id IS NULL)", name="member_id_six_digits"),
    )

class Membership(db.Model):
    __tablename__ = "membership"
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    annee = db.Column(db.Integer, nullable=False)       # année de début (2025 => 2025-2026)
    annee_code = db.Column(db.String, nullable=False)   # ex: EA-23

    __table_args__ = (
        db.UniqueConstraint("user_id", "annee", name="uq_user_annee"),        # 1 carte max par user et par année
        db.UniqueConstraint("annee", "annee_code", name="uq_annee_code_year") # code unique dans une même année
    )

class PendingRegistration(db.Model):
    __tablename__ = "pending_registration"
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    nom = db.Column(db.String(100), nullable=False)
    prenom = db.Column(db.String(100), nullable=False)
    member_id = db.Column(db.String(6), unique=True, nullable=True)
    email = db.Column(db.String(254), unique=True, nullable=True)
    password_hash = db.Column(db.String, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)

    __table_args__ = (
        db.CheckConstraint("(member_id IS NOT NULL) <> (email IS NOT NULL)", name="pending_registration_one_identifier"),
    )

class PendingCardRequest(db.Model):
    __tablename__ = "pending_card_request"
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    annee = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    status = db.Column(db.String(16), nullable=False, default="pending")
    user = relationship("User")

    __table_args__ = (db.UniqueConstraint("user_id", "annee", name="uq_pending_card_user_year"),)

class Room(db.Model):
    __tablename__ = "room"
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = db.Column(db.String, nullable=False)
    code = db.Column(db.String(12), unique=True, nullable=False, index=True)
    password = db.Column(db.String, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)
    created_by = db.Column(db.String, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)

    @staticmethod
    def generate_code(length=6):
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    def generate_password(length=10):
        alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        return "".join(secrets.choice(alphabet) for _ in range(length))

class VoteSession(db.Model):
    __tablename__ = "vote_session"
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    room_id = db.Column(db.String, db.ForeignKey("room.id", ondelete="CASCADE"), nullable=False, index=True)
    question = db.Column(db.String, nullable=False)
    status = db.Column(db.String, nullable=False, default="open")  # open | closed
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    closed_at = db.Column(db.DateTime, nullable=True)

    options = relationship("VoteOption", backref="session", cascade="all, delete-orphan")

class VoteOption(db.Model):
    __tablename__ = "vote_option"
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = db.Column(db.String, db.ForeignKey("vote_session.id", ondelete="CASCADE"), nullable=False, index=True)
    text = db.Column(db.String, nullable=False)

class VoteBallot(db.Model):
    __tablename__ = "vote_ballot"
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = db.Column(db.String, db.ForeignKey("vote_session.id", ondelete="CASCADE"), nullable=False, index=True)
    option_id = db.Column(db.String, db.ForeignKey("vote_option.id", ondelete="CASCADE"), nullable=False, index=True)
    voter_token = db.Column(db.String, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("session_id", "voter_token", name="uq_vote_once_per_session"),
    )

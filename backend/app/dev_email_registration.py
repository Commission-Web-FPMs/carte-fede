"""Validation contract for native DEV email enrollment (no identity mutations).

The caller is feature gated until the native flow and deployment gates pass.
Passwords and email tokens never enter this module.
"""
import re
from dataclasses import dataclass


class EnrollmentContractError(ValueError):
    """Invalid intake or incomplete native proof; grants no authorization."""


@dataclass(frozen=True)
class Intake:
    nom: str
    prenom: str
    member_id: str | None
    email: str

    def pending_identifier(self):
        # Existing pending_registration enforces matricule XOR email. Keep its
        # schema; derive the verification email again from the matricule.
        return {"member_id": self.member_id, "email": None if self.member_id else self.email}


def normalize_intake(data):
    if not isinstance(data, dict) or set(data) != {"nom", "prenom", "identifier"}:
        raise EnrollmentContractError("Trois champs métier exclusivement requis.")
    if any(not isinstance(v, str) for v in data.values()):
        raise EnrollmentContractError("Informations invalides.")
    values = {k: v.strip() for k, v in data.items()}
    if any(re.search(r"[\x00-\x1f\x7f]", v) for v in data.values()):
        raise EnrollmentContractError("Caractères de contrôle interdits.")
    if any(not 1 <= len(values[k]) <= 100 for k in ("nom", "prenom")):
        raise EnrollmentContractError("Nom et prénom requis.")
    identifier = values["identifier"].lower()
    if re.fullmatch(r"[0-9]{6}", identifier):
        member_id, email = identifier, identifier + "@umons.ac.be"
    elif (len(identifier) <= 254 and re.fullmatch(
            r"[^@\s<>(),;:\\\[\]\"]+@[^@\s<>(),;:\\\[\]\"]+\.[^@\s<>(),;:\\\[\]\"]+", identifier)):
        email = identifier
        match = re.fullmatch(r"([0-9]{6})@umons\.ac\.be", email)
        member_id = match.group(1) if match else None
    else:
        raise EnrollmentContractError("Matricule de six chiffres ou adresse e-mail requis.")
    return Intake(values["nom"], values["prenom"], member_id, email)


def capture_recipient_allowed(intake, synthetic_matricules=()):
    """Capture is not proof of ownership of an arbitrary real address."""
    if intake.member_id:
        return intake.member_id in synthetic_matricules
    return intake.email.endswith("@example.invalid")


def require_native_proof(user, subject, expected_email, proof_id):
    """Require server-persisted native proof, not browser claims or a pending row.

    The caller must read this user from Authentik through its scoped API and
    require a signed native completion event. This predicate alone must never
    be exposed as an enrollment endpoint.
    """
    attrs = user.get("attributes", {})
    if (not isinstance(attrs, dict)
            or str(user.get("uuid")) != subject
            or user.get("path") != "users/carte-fede-dev-enrollment"
            or user.get("type") != "internal"
            or user.get("is_superuser") or user.get("roles")
            or attrs.get("carte_fede_dev_owned") is not True
            or user.get("email", "").lower() != expected_email
            or attrs.get("carte_fede_dev_verified_email") != expected_email
            or not isinstance(proof_id, str) or not 32 <= len(proof_id) <= 128
            or attrs.get("carte_fede_dev_email_proof") != proof_id
            or attrs.get("carte_fede_dev_password_initialized") is not True):
        raise EnrollmentContractError("Vérification native incomplète.")

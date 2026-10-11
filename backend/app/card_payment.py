from decimal import Decimal, InvalidOperation
from io import BytesIO
import re
import os
from types import SimpleNamespace

import qrcode
from flask import Blueprint, jsonify, request, send_file
from flask_login import current_user

from .models import CardPaymentSettings, db
from .routes_memberships import current_academic_year

bp_payment = Blueprint("card_payment", __name__)


DEMO_IBAN = "DE36000000000000000000"  # checksum valid; bank/account all zero, no real destination

def development_payment():
    return os.getenv("APP_ENV") == "development" and os.getenv("AUTH_MODE") == "oidc"

def settings():
    if development_payment():
        row = db.session.get(CardPaymentSettings, 2)
        if row:
            # Fail closed even if someone edits DEV SQL to real bank details.
            return SimpleNamespace(beneficiary=row.beneficiary, iban=DEMO_IBAN, bic="", amount=row.amount, communication_prefix=row.communication_prefix)
        return SimpleNamespace(beneficiary="TEST Carte Fede DEV", iban=DEMO_IBAN, bic="", amount=Decimal("0.01"), communication_prefix="TEST SANS PAIEMENT")
    return db.session.get(CardPaymentSettings, 1)


def public_settings():
    row = settings()
    return {
        "annee": current_academic_year(),
        "test_mode": development_payment(),
        "beneficiary": row.beneficiary if row else "",
        "iban": row.iban if row else "",
        "bic": row.bic if row else "",
        "amount": str(row.amount) if row and row.amount is not None else "",
        "communication_prefix": row.communication_prefix if row else "Carte Fédé",
    }


def valid_iban(value):
    if not re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}", value):
        return False
    rearranged = value[4:] + value[:4]
    digits = "".join(str(int(char, 36)) if char.isalpha() else char for char in rearranged)
    return int(digits) % 97 == 1


def parse_settings(data):
    if not isinstance(data, dict) or any(not isinstance(data.get(key, ""), str) for key in ("beneficiary", "iban", "bic", "amount", "communication_prefix")):
        raise ValueError("Paramètres invalides.")
    beneficiary = data.get("beneficiary", "").strip()
    iban = re.sub(r"\s+", "", data.get("iban", "")).upper()
    bic = data.get("bic", "").strip().upper()
    prefix = data.get("communication_prefix", "Carte Fédé").strip()
    if any(re.search(r"[\x00-\x1f\x7f]", value) for value in (beneficiary, bic, prefix)):
        raise ValueError("Les caractères de contrôle ne sont pas autorisés.")
    if not beneficiary or len(beneficiary) > 70 or not iban or not valid_iban(iban):
        raise ValueError("Nom du bénéficiaire ou IBAN invalide.")
    if bic and not re.fullmatch(r"[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?", bic):
        raise ValueError("BIC invalide.")
    if not prefix or len(prefix) > 60:
        raise ValueError("Préfixe de communication invalide.")
    try:
        amount = Decimal(data.get("amount", ""))
    except InvalidOperation:
        raise ValueError("Montant invalide.") from None
    if not amount.is_finite() or amount < Decimal("0.01") or amount > Decimal("99999999.99") or amount.as_tuple().exponent < -2:
        raise ValueError("Le montant doit être positif, en euros, avec deux décimales maximum.")
    if development_payment():
        if iban != DEMO_IBAN or bic:
            raise ValueError("DEV : seul l’IBAN fictif affiché est accepté, BIC vide.")
        if not beneficiary.startswith("TEST ") or not prefix.startswith("TEST "):
            raise ValueError("DEV : bénéficiaire et communication doivent commencer par TEST.")
    return beneficiary, iban, bic, amount, prefix


def epc_payload(row, communication):
    return "\n".join(("BCD", "002", "1", "SCT", row.bic, row.beneficiary, row.iban,
                      f"EUR{row.amount:.2f}", "", "", communication))


@bp_payment.get("/api/card-payment")
def get_card_payment():
    response = jsonify(public_settings())
    response.headers["Cache-Control"] = "no-store"
    if development_payment():
        response.headers["X-Carte-Fede-Test"] = "non-payable-demo"
    return response


@bp_payment.post("/api/card-payment/qr")
def payment_qr():
    row = settings()
    if not row or not row.beneficiary or not row.iban or row.amount is None:
        return jsonify({"error": "Le paiement par QR n'est pas encore configuré."}), 503
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Données invalides."}), 400
    if development_payment():
        data.setdefault("nom","TEST");data.setdefault("prenom","DEMO")
    nom = data.get("nom") or (current_user.nom if current_user.is_authenticated else "")
    prenom = data.get("prenom") or (current_user.prenom if current_user.is_authenticated else "")
    if not isinstance(nom, str) or not isinstance(prenom, str) or not nom.strip() or not prenom.strip():
        return jsonify({"error": "Nom et prénom requis pour la communication."}), 400
    year = data.get("annee", current_academic_year())
    if type(year) is not int or year not in (current_academic_year(), current_academic_year() + 1):
        return jsonify({"error": "Année académique invalide."}), 400
    # Never encode copied personal names into a demonstration payment QR.
    communication = (f"TEST DEMO – {row.communication_prefix} {year}-{year + 1}" if development_payment()
                     else f"{nom.strip().upper()} {prenom.strip()} – {row.communication_prefix} {year}-{year + 1}")
    if len(communication) > 140 or re.search(r"[\x00-\x1f\x7f]", communication):
        return jsonify({"error": "Communication trop longue ou invalide."}), 400
    payload = epc_payload(row, communication)
    if len(payload.encode("utf-8")) > 331:
        return jsonify({"error": "Données de paiement trop longues pour un QR EPC."}), 400
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=4)
    qr.add_data(payload.encode("utf-8"))
    qr.make(fit=True)
    if qr.version > 13:
        return jsonify({"error": "Données de paiement trop longues pour un QR EPC."}), 400
    output = BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(output, format="PNG")
    output.seek(0)
    response = send_file(output, mimetype="image/png")
    response.headers["Cache-Control"] = "no-store"
    if development_payment():
        response.headers["X-Carte-Fede-Test"] = "non-payable-demo"
    return response

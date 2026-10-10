"""End-to-end request flow against a disposable PostgreSQL database.

Run with DATABASE_URL and AUTO_CREATE_DB=1; never point at production data.
"""

import os
import unittest
from datetime import datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app
from app.models import db, CardPaymentSettings, Membership, PendingCardRequest, PendingRegistration, Role, User
from app.routes_memberships import current_academic_year
from app.card_payment import epc_payload


class RequestsFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert os.environ.get("DATABASE_URL", "").startswith("postgresql+psycopg://postgres:postgres@127.0.0.1:15432/")
        assert os.environ.get("AUTO_CREATE_DB") == "1"
        cls.app = create_app()

    def setUp(self):
        with self.app.app_context():
            db.drop_all()
            db.create_all()
            db.session.add(User(member_id="999999", nom="Admin", prenom="Test",
                                password_hash=generate_password_hash("admin-test-password"), role=Role.ADMIN))
            db.session.commit()
        self.public = self.app.test_client()
        self.admin = self.app.test_client()
        self.member = self.app.test_client()

    @staticmethod
    def post(client, path, payload=None):
        return client.post(path, json=payload or {}, base_url="https://localhost")

    @staticmethod
    def get(client, path):
        return client.get(path, base_url="https://localhost")

    def test_registration_and_card_approval(self):
        year = current_academic_year()
        pending = {"nom": "Dupont", "prenom": "Élodie", "member_id": "123456",
                   "password": "secret-1234", "password2": "secret-1234"}
        self.assertEqual(self.get(self.public, "/api/admin/requests").status_code, 401)
        self.assertEqual(self.post(self.public, "/api/auth/register", ["invalid"]).status_code, 400)
        self.assertEqual(self.post(self.public, "/api/auth/register", {**pending, "member_id": "abc"}).status_code, 400)
        self.assertEqual(self.post(self.public, "/api/auth/register", {**pending, "password2": "wrong"}).status_code, 400)
        self.assertEqual(self.post(self.public, "/api/auth/register", pending).status_code, 202)
        self.assertEqual(self.post(self.public, "/api/auth/register", pending).status_code, 409)

        self.assertEqual(self.post(self.member, "/api/auth/login", {"identifiant": "123456", "password": "secret-1234"}).status_code, 401)
        with self.app.app_context():
            self.assertIsNone(User.query.filter_by(member_id="123456").first())
            row = PendingRegistration.query.filter_by(member_id="123456").one()
            self.assertNotEqual(row.password_hash, "secret-1234")
            self.assertTrue(check_password_hash(row.password_hash, "secret-1234"))
            request_id = row.id

        self.assertEqual(self.post(self.admin, "/api/auth/login", {"identifiant": "999999", "password": "admin-test-password"}).status_code, 200)
        self.assertEqual(len(self.get(self.admin, "/api/admin/requests").json["registrations"]), 1)
        self.assertEqual(self.post(self.admin, f"/api/admin/registrations/{request_id}/approve",
                                   {"add_card": True, "annee": year, "prefix": "F"}).status_code, 200)
        with self.app.app_context():
            user = User.query.filter_by(member_id="123456").one()
            self.assertEqual(user.role, Role.MEMBER)
            self.assertEqual(Membership.query.filter_by(user_id=user.id, annee=year).one().annee_code, "F-1")
            self.assertEqual(PendingRegistration.query.count(), 0)
        self.assertEqual(self.post(self.member, "/api/auth/login", {"identifiant": "123456", "password": "secret-1234"}).status_code, 200)
        self.assertEqual(self.get(self.member, "/api/admin/requests").status_code, 403)
        self.assertEqual(self.post(self.member, "/api/memberships/requests", {"annee": year}).status_code, 409)
        self.assertEqual(self.post(self.member, "/api/memberships/requests", {"annee": 9999}).status_code, 400)
        self.assertEqual(self.post(self.member, "/api/memberships/requests", {"annee": float(year) + .5}).status_code, 400)
        self.assertEqual(self.post(self.member, "/api/memberships/requests", {"annee": year + 1}).status_code, 202)
        self.assertEqual(self.post(self.member, "/api/memberships/requests", {"annee": year + 1}).status_code, 409)
        self.assertEqual(self.get(self.member, "/api/memberships/requests").json[0]["status"], "payment_required")
        with self.app.app_context():
            card_id = PendingCardRequest.query.one().id
        self.assertEqual(self.post(self.admin, f"/api/admin/card-requests/{card_id}/reject").status_code, 200)
        self.assertEqual(self.get(self.member, "/api/memberships/requests").json[0]["status"], "rejected")
        self.assertEqual(self.post(self.member, "/api/memberships/requests", {"annee": year + 1}).status_code, 202)
        self.assertEqual(self.post(self.admin, f"/api/admin/card-requests/{card_id}/approve", {"prefix": "EA"}).status_code, 409)
        self.assertEqual(self.post(self.admin, f"/api/admin/card-requests/{card_id}/payment-received").status_code, 200)
        self.assertEqual(self.post(self.admin, f"/api/admin/card-requests/{card_id}/approve", {"prefix": "EA"}).status_code, 200)
        with self.app.app_context():
            self.assertEqual(Membership.query.filter_by(annee=year + 1).one().annee_code, "EA-1")
            self.assertEqual(PendingCardRequest.query.count(), 0)
        self.assertEqual(self.post(self.public, "/api/auth/register", pending).status_code, 409)

    def test_pending_queue_is_readonly_and_retains_expired_rows(self):
        from sqlalchemy import event
        with self.app.app_context():
            expired = PendingRegistration(email="expired@synthetic.invalid", nom="Expired", prenom="Fixture",
                password_hash=generate_password_hash("synthetic-password"), expires_at=datetime.utcnow()-timedelta(days=1))
            active = PendingRegistration(email="active@synthetic.invalid", nom="Active", prenom="Fixture",
                password_hash=generate_password_hash("synthetic-password"), expires_at=datetime.utcnow()+timedelta(days=1))
            db.session.add_all([expired, active])
            db.session.commit()
            expired_id, active_id = expired.id, active.id
            engine = db.engine
        self.assertEqual(self.post(self.admin, "/api/auth/login", {"identifiant":"999999", "password":"admin-test-password"}).status_code, 200)
        def forbid_write(conn, cursor, statement, parameters, context, executemany):
            self.assertEqual(statement.lstrip().split(None, 1)[0].upper(), "SELECT")
        event.listen(engine, "before_cursor_execute", forbid_write)
        try:
            response = self.get(self.admin, "/api/admin/requests")
            self.assertEqual(response.status_code, 200)
            self.assertEqual([row["id"] for row in response.json["registrations"]], [active_id])
        finally:
            event.remove(engine, "before_cursor_execute", forbid_write)
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(PendingRegistration, expired_id))


    def test_non_umons_registration_with_email(self):
        year = current_academic_year()
        payload = {"nom": "Bernard", "prenom": "Alice", "email": " Alice@Example.org ",
                   "password": "secret-1234", "password2": "secret-1234"}
        self.assertEqual(self.post(self.public, "/api/auth/register", {**payload, "email": "alice@"}).status_code, 400)
        self.assertEqual(self.post(self.public, "/api/auth/register", {**payload, "member_id": "123456"}).status_code, 400)
        self.assertEqual(self.post(self.public, "/api/auth/register", {**payload, "email": None}).status_code, 400)
        with self.app.app_context():
            db.session.add(User(email="Existing@Example.org", nom="Existing", prenom="Test",
                                password_hash=generate_password_hash("secret-1234")))
            db.session.commit()
        self.assertEqual(self.post(self.public, "/api/auth/register", {**payload, "email": "existing@example.org"}).status_code, 409)
        self.assertEqual(self.post(self.public, "/api/auth/register", payload).status_code, 202)
        self.assertEqual(self.post(self.public, "/api/auth/register", {**payload, "email": "ALICE@example.org"}).status_code, 409)
        self.assertEqual(self.post(self.member, "/api/auth/login", {"email": "alice@example.org", "password": "secret-1234"}).status_code, 401)
        with self.app.app_context():
            row = PendingRegistration.query.filter_by(email="alice@example.org").one()
            self.assertIsNone(row.member_id)
            self.assertTrue(check_password_hash(row.password_hash, "secret-1234"))
            request_id = row.id
        self.assertEqual(self.post(self.admin, "/api/auth/login", {"identifiant": "999999", "password": "admin-test-password"}).status_code, 200)
        registration = self.get(self.admin, "/api/admin/requests").json["registrations"][0]
        self.assertIsNone(registration["member_id"])
        self.assertEqual(registration["email"], "alice@example.org")
        self.assertEqual(self.post(self.admin, f"/api/admin/registrations/{request_id}/approve",
                                   {"add_card": True, "annee": year, "prefix": "E"}).status_code, 200)
        with self.app.app_context():
            user = User.query.filter_by(email="alice@example.org").one()
            self.assertIsNone(user.member_id)
            self.assertEqual(Membership.query.filter_by(user_id=user.id, annee=year).one().annee_code, "E-1")
        self.assertEqual(self.post(self.member, "/api/auth/login", {"email": "ALICE@example.org", "password": "secret-1234"}).status_code, 200)

    def test_expiry_and_rejection(self):
        payload = {"nom": "Martin", "prenom": "Anne", "member_id": "654321",
                   "password": "secret-5678", "password2": "secret-5678"}
        self.assertEqual(self.post(self.public, "/api/auth/register", payload).status_code, 202)
        with self.app.app_context():
            row = PendingRegistration.query.one()
            expired_id = row.id
            row.expires_at = datetime.utcnow() - timedelta(seconds=1)
            db.session.commit()
        self.post(self.admin, "/api/auth/login", {"identifiant": "999999", "password": "admin-test-password"})
        self.assertEqual(self.post(self.admin, f"/api/admin/registrations/{expired_id}/approve").status_code, 404)
        self.assertEqual(self.get(self.admin, "/api/admin/requests").json["registrations"], [])
        self.assertEqual(self.post(self.public, "/api/auth/register", payload).status_code, 202)
        with self.app.app_context():
            request_id = PendingRegistration.query.one().id
        self.assertEqual(self.post(self.admin, f"/api/admin/registrations/{request_id}/reject").status_code, 200)
        with self.app.app_context():
            self.assertEqual(PendingRegistration.query.count(), 0)
            self.assertIsNone(User.query.filter_by(member_id="654321").first())

    def test_approval_without_card_and_manual_fulfillment(self):
        year = current_academic_year()
        payload = {"nom": "Leroy", "prenom": "Paul", "member_id": "456789",
                   "password": "secret-9012", "password2": "secret-9012"}
        self.assertEqual(self.post(self.public, "/api/auth/register", payload).status_code, 202)
        with self.app.app_context():
            request_id = PendingRegistration.query.one().id
        self.post(self.admin, "/api/auth/login", {"identifiant": "999999", "password": "admin-test-password"})
        self.assertEqual(self.post(self.admin, f"/api/admin/registrations/{request_id}/approve").status_code, 200)
        with self.app.app_context():
            user = User.query.filter_by(member_id="456789").one()
            user_id = user.id
            self.assertEqual(Membership.query.filter_by(user_id=user_id).count(), 0)
            self.assertEqual(PendingCardRequest.query.filter_by(user_id=user_id).one().status, "payment_required")
        self.post(self.member, "/api/auth/login", {"identifiant": "456789", "password": "secret-9012"})
        self.assertEqual(self.post(self.member, "/api/memberships/requests", {"annee": year}).status_code, 409)
        self.assertEqual(self.admin.put(f"/api/admin/users/{user_id}/annees", base_url="https://localhost",
                                        json={"annee": f"{year}-{year + 1}", "prefix": "MI"}).status_code, 200)
        with self.app.app_context():
            self.assertEqual(Membership.query.filter_by(user_id=user_id).one().annee_code, "MI-1")
            self.assertEqual(PendingCardRequest.query.count(), 0)

    def test_free_bac1_and_payment_settings(self):
        year = current_academic_year()
        payload = {"nom": "Petit", "prenom": "Camille", "member_id": "345678",
                   "password": "secret-1234", "password2": "secret-1234", "free_card_requested": True}
        self.assertEqual(self.post(self.public, "/api/auth/register", payload).status_code, 202)
        with self.app.app_context():
            row = PendingRegistration.query.one()
            self.assertTrue(row.free_card_requested)
            self.assertEqual(row.card_year, year)
            request_id = row.id
        self.post(self.admin, "/api/auth/login", {"identifiant": "999999", "password": "admin-test-password"})
        self.assertTrue(self.get(self.admin, "/api/admin/requests").json["registrations"][0]["free_card_requested"])
        self.assertEqual(self.post(self.admin, f"/api/admin/registrations/{request_id}/approve").status_code, 200)
        with self.app.app_context():
            self.assertEqual(Membership.query.count(), 0)
            card = PendingCardRequest.query.one()
            self.assertTrue(card.free_card)
            self.assertEqual(card.status, "pending")
            self.assertEqual(card.annee, year)
            card_id = card.id
        self.assertEqual(self.post(self.admin, f"/api/admin/card-requests/{card_id}/payment-received").status_code, 409)
        self.assertEqual(self.post(self.admin, f"/api/admin/card-requests/{card_id}/reject").status_code, 200)
        with self.app.app_context():
            self.assertEqual(Membership.query.count(), 0)
            self.assertEqual(PendingCardRequest.query.one().status, "rejected")

        valid = {"beneficiary": "Fédé Polytech", "iban": "BE68539007547034", "bic": "", "amount": "12.50", "communication_prefix": "Carte Fédé"}
        self.assertEqual(self.public.get("/api/card-payment").json["beneficiary"], "")
        self.assertEqual(self.public.get("/api/admin/card-payment").status_code, 401)
        self.assertEqual(self.admin.put("/api/admin/card-payment", json={**valid, "iban": "BE00000000000000"}, base_url="https://localhost").status_code, 400)
        self.assertEqual(self.admin.put("/api/admin/card-payment", json={**valid, "amount": "NaN"}, base_url="https://localhost").status_code, 400)
        self.assertEqual(self.admin.put("/api/admin/card-payment", json=valid, base_url="https://localhost").status_code, 200)
        self.assertEqual(self.public.get("/api/card-payment").json["annee"], year)
        qr = self.post(self.public, "/api/card-payment/qr", {"nom": "Petit", "prenom": "Camille"})
        self.assertEqual(qr.status_code, 200)
        self.assertEqual(qr.mimetype, "image/png")
        self.assertTrue(qr.data.startswith(b"\x89PNG"))
        with self.app.app_context():
            payload = epc_payload(db.session.get(CardPaymentSettings, 1), f"PETIT Camille – Carte Fédé {year}-{year + 1}")
            self.assertEqual(payload.split("\n")[:4], ["BCD", "002", "1", "SCT"])
            self.assertEqual(payload.split("\n")[7], "EUR12.50")
            self.assertTrue(payload.endswith(f"PETIT Camille – Carte Fédé {year}-{year + 1}"))
        self.assertEqual(self.post(self.public, "/api/card-payment/qr", {"nom": "Petit", "prenom": "Camille", "annee": year + 2}).status_code, 400)


if __name__ == "__main__":
    unittest.main()

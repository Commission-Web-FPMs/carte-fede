"""Synthetic intake/proof contract: no network, database or real identities."""
import unittest
from app.dev_email_registration import (
    EnrollmentContractError, normalize_intake, capture_recipient_allowed,
    require_native_proof,
)


class EmailEnrollmentContract(unittest.TestCase):
    def intake(self, identifier="990801", **extra):
        return normalize_intake(dict(nom="Test", prenom="Synthétique", identifier=identifier, **extra))

    def test_matricule_and_email_share_canonical_collision_key(self):
        a, b = self.intake(), self.intake("990801@UMONS.AC.BE")
        self.assertEqual(a, b)
        self.assertEqual(a.email, "990801@umons.ac.be")
        self.assertEqual(a.pending_identifier(), {"member_id": "990801", "email": None})
        self.assertEqual(self.intake("test@example.invalid").pending_identifier(),
                         {"member_id": None, "email": "test@example.invalid"})

    def test_no_credentials_privileges_or_card_options_at_intake(self):
        for key, value in [("password", "secret"), ("role", "ADMIN"),
                           ("groups", ["membres"]), ("free_card_requested", True),
                           ("subject", "forged"), ("username", "chosen")]:
            with self.subTest(key=key), self.assertRaises(EnrollmentContractError):
                self.intake(**{key: value})

    def test_invalid_and_header_injection_rejected(self):
        for identifier in ["", "12345", "1234567", "a@b", "a@b.test\r\nBcc: victim@test.invalid", 'a<@b.test', "a@b.test c"]:
            with self.subTest(identifier=identifier), self.assertRaises(EnrollmentContractError):
                self.intake(identifier)

    def test_capture_cannot_verify_real_address(self):
        self.assertTrue(capture_recipient_allowed(self.intake("test@example.invalid")))
        self.assertFalse(capture_recipient_allowed(self.intake("test@example.invalid.attacker.test")))
        self.assertFalse(capture_recipient_allowed(self.intake()))
        self.assertTrue(capture_recipient_allowed(self.intake(), ("990801",)))
        self.assertFalse(capture_recipient_allowed(self.intake("230466"), ("990801",)))

    def proof_user(self):
        return dict(uuid="synthetic-sub", email="test@example.invalid", type="internal",
                    path="users/carte-fede-dev-enrollment", is_superuser=False, roles=[],
                    attributes=dict(carte_fede_dev_owned=True,
                                    carte_fede_dev_verified_email="test@example.invalid",
                                    carte_fede_dev_email_proof="p" * 32,
                                    carte_fede_dev_password_initialized=True))

    def verify(self, user, **override):
        args=dict(subject="synthetic-sub", expected_email="test@example.invalid", proof_id="p" * 32)
        args.update(override)
        require_native_proof(user, **args)

    def test_email_password_subject_and_owned_scope_all_required(self):
        self.verify(self.proof_user())
        for key, value in [("uuid", "other"), ("email", "other@example.invalid"),
                           ("path", "users/carte-fede"), ("type", "external"),
                           ("is_superuser", True), ("roles", ["admin"])]:
            u=self.proof_user();u[key]=value
            with self.subTest(key=key), self.assertRaises(EnrollmentContractError): self.verify(u)
        for key in self.proof_user()["attributes"]:
            u=self.proof_user();del u["attributes"][key]
            with self.subTest(attribute=key), self.assertRaises(EnrollmentContractError): self.verify(u)
        with self.assertRaises(EnrollmentContractError): self.verify(self.proof_user(), proof_id="q" * 32)


if __name__ == "__main__":
    unittest.main()

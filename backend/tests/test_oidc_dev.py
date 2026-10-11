import os, time, unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from app.oidc_dev import verify_claims, bound_dev_uuid

class OIDCSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    def setUp(self):
        self.issuer='https://auth.fede.fpms.ac.be/application/o/carte-fede-dev/'
        self.claims=dict(iss=self.issuer,sub='synthetic-sub',aud='carte-fede-dev',exp=int(time.time())+300,
            iat=int(time.time()),nonce='synthetic-nonce',carte_fede_uuid='synthetic-business-uuid',carte_fede_dev_allowed=True)
        self.bindings={'synthetic-sub':'synthetic-business-uuid'}
    def validate(self,claims=None,key=None,algorithm='RS256'):
        encoded=jwt.encode(claims or self.claims,key or self.key,algorithm=algorithm)
        return verify_claims(encoded,self.key.public_key(),self.issuer,'carte-fede-dev','synthetic-nonce',self.bindings)
    def test_valid_signature_and_binding(self):self.assertEqual(self.validate()['sub'],'synthetic-sub')
    def test_invalid_security_claims(self):
        for k,v in [('iss',self.issuer+'other'),('aud','carte-fede-main'),('nonce','wrong'),('exp',int(time.time())-90),('iat',int(time.time())+100),('sub','unknown'),('carte_fede_uuid','other'),('carte_fede_dev_allowed',False),('azp','carte-fede-main')]:
            with self.subTest(k=k),self.assertRaises((ValueError,jwt.PyJWTError)):self.validate(dict(self.claims,**{k:v}))
    def test_missing_claims(self):
        for k in ['iss','sub','aud','nonce','exp','iat','carte_fede_uuid','carte_fede_dev_allowed']:
            d=self.claims.copy();d.pop(k)
            with self.subTest(k=k),self.assertRaises((ValueError,jwt.PyJWTError)):self.validate(d)
    def test_wrong_signature(self):
        with self.assertRaises(jwt.PyJWTError):self.validate(key=rsa.generate_private_key(public_exponent=65537,key_size=2048))
    def test_hmac_rejected(self):
        encoded=jwt.encode(self.claims,'synthetic-key',algorithm='HS256')
        with self.assertRaises(jwt.PyJWTError):verify_claims(encoded,self.key.public_key(),self.issuer,'carte-fede-dev','synthetic-nonce',self.bindings)
    def test_multi_audience_needs_authorized_party(self):
        with self.assertRaises(ValueError):self.validate(dict(self.claims,aud=['carte-fede-dev','other']))
    def test_existing_account_has_distinct_deterministic_dev_uuid(self):
        subject='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        identity=bound_dev_uuid(subject,self.bindings)
        self.assertNotEqual(identity,subject)
        self.assertEqual(identity,bound_dev_uuid(subject,self.bindings))
        self.assertEqual(self.validate(dict(self.claims,sub=subject,carte_fede_uuid=identity))['sub'],subject)
        with self.assertRaises(ValueError):self.validate(dict(self.claims,sub=subject,carte_fede_uuid='synthetic-business-uuid'))
    def test_unknown_noncanonical_subject_refused(self):
        for value in ['unknown','AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA',None]:
            with self.assertRaises((ValueError,TypeError,AttributeError)):bound_dev_uuid(value,self.bindings)
    def dev_env(self):
        return dict(APP_ENV='development',AUTH_MODE='oidc',DATABASE_URL='postgresql+psycopg://carte_fede_dev:synthetic@localhost/carte_fede_dev',SECRET_KEY='synthetic-test-key',FRONTEND_BASE_URL='https://carte-dev.fede.fpms.ac.be',OIDC_ISSUER_URL=self.issuer,OIDC_CLIENT_ID='carte-fede-dev',OIDC_CLIENT_SECRET='synthetic-only',OIDC_IDENTITY_BINDINGS='{"synthetic-sub":"synthetic-business-uuid"}',AUTO_CREATE_DB='0')
    def test_production_database_refused_before_sql(self):
        from app import create_app
        with patch.dict(os.environ,dict(self.dev_env(),DATABASE_URL='postgresql+psycopg://carte_fede_main:synthetic@localhost/carte_fede_main')),self.assertRaises(RuntimeError):create_app()
    def test_auto_create_cannot_connect_to_production(self):
        from app import create_app
        with patch.dict(os.environ,dict(self.dev_env(),DATABASE_URL='postgresql+psycopg://carte_fede_main:synthetic@localhost/carte_fede_main',AUTO_CREATE_DB='1')),patch('app.db.create_all') as create:
            with self.assertRaises(RuntimeError):create_app()
            create.assert_not_called()
    def test_public_dev_cannot_fall_back_to_local_auth(self):
        from app import create_app
        with patch.dict(os.environ,dict(self.dev_env(),AUTH_MODE='flask')),self.assertRaises(RuntimeError):create_app()
    def test_anonymous_sensitive_routes_refused(self):
        from app import create_app
        with patch.dict(os.environ,self.dev_env()):app=create_app()
        client=app.test_client()
        for path in ['/api/me','/api/admin/users','/verify']:
            self.assertEqual(client.get(path).status_code,401)
        for path in ['/api/auth/login','/api/auth/register','/api/card-payment/qr']:
            self.assertEqual(client.post(path).status_code,403)
    def test_existing_account_cannot_gain_elevated_role_during_session(self):
        from app import create_app
        from app.models import Role
        subject='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        identity=bound_dev_uuid(subject,self.bindings)
        with patch.dict(os.environ,self.dev_env()):app=create_app()
        c=app.test_client()
        with c.session_transaction() as session:
            session.update(oidc_sub=subject,oidc_access_token='synthetic-token',oidc_expires_at=time.time()+200)
        with patch('app.oidc_dev.current_user') as user,patch('app.oidc_dev.requests.get') as get,patch('app.oidc_dev.requests.post'):
            user.is_authenticated=True;user.id=identity;user.role=Role.ADMIN
            get.return_value.json.return_value={'sub':subject,'carte_fede_uuid':identity,'carte_fede_dev_allowed':True}
            self.assertEqual(c.get('/api/admin/users').status_code,401)
    def test_pkce_state_nonce_and_no_open_redirect(self):
        from app import create_app
        with patch.dict(os.environ,self.dev_env()):app=create_app()
        client=app.test_client();r=client.get('/api/auth/oidc/login?next=//evil.invalid')
        q=parse_qs(urlsplit(r.location).query)
        self.assertEqual(q['code_challenge_method'],['S256']);self.assertTrue(q['state']);self.assertTrue(q['nonce'])
        with client.session_transaction() as s:self.assertEqual(s['oidc_next'],'/');self.assertNotIn(s['oidc_verifier'],r.location)
        self.assertNotIn('synthetic-only',r.headers.get('Set-Cookie',''))
    def test_wrong_and_replayed_state_no_token_exchange(self):
        from app import create_app
        with patch.dict(os.environ,self.dev_env()):app=create_app()
        c=app.test_client();c.get('/api/auth/oidc/login')
        with patch('app.oidc_dev.requests.post') as post:
            self.assertEqual(c.get('/api/auth/oidc/callback?code=bad&state=wrong').status_code,401)
            self.assertEqual(c.get('/api/auth/oidc/callback?code=bad&state=wrong').status_code,401);post.assert_not_called()

if __name__=='__main__':unittest.main()

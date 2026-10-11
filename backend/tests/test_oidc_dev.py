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
    def test_unmapped_identity_never_receives_a_profile(self):
        from app.oidc_dev import get_dev_user
        with patch('app.oidc_dev.db.session') as database:
            with self.assertRaises(ValueError):get_dev_user('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',self.bindings)
            database.get.assert_not_called();database.add.assert_not_called();database.commit.assert_not_called()
    def test_database_role_is_not_overwritten(self):
        from app.oidc_dev import get_dev_user
        from app.models import Role
        for role in [Role.ADMIN,Role.VERIFIER,Role.MEMBER]:
            with patch('app.oidc_dev.db.session') as database:
                database.get.return_value.role=role
                user=get_dev_user('synthetic-sub',self.bindings)
                self.assertEqual(user.role,role);database.add.assert_not_called();database.commit.assert_not_called()
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
    def test_synthetic_initializer_refuses_production_copy_before_sql(self):
        import runpy
        from pathlib import Path
        with patch.dict(os.environ,dict(self.dev_env(),DEV_DATA_MODE='production_copy')),patch('app.create_app') as create:
            with self.assertRaisesRegex(AssertionError,'Synthetic initialization forbidden'):
                runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/init_dev_data.py'))
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
        for path in ['/api/auth/login','/api/auth/register']:
            self.assertEqual(client.post(path).status_code,403)
    def test_database_roles_and_session_role_changes(self):
        from app import create_app
        from app.models import Role
        with patch.dict(os.environ,self.dev_env()):app=create_app()
        @app.get('/api/test-role')
        def role_probe():
            from app.oidc_dev import current_user
            return {'role':current_user.role.value}
        c=app.test_client()
        with c.session_transaction() as session:
            session.update(oidc_sub='synthetic-sub',oidc_access_token='synthetic-token',oidc_expires_at=time.time()+200)
        with patch('app.oidc_dev.current_user') as user,patch('app.oidc_dev.requests.get') as get,patch('app.oidc_dev.requests.post'):
            user.is_authenticated=True;user.id='synthetic-business-uuid'
            get.return_value.json.return_value={'sub':'synthetic-sub','carte_fede_uuid':'synthetic-business-uuid','carte_fede_dev_allowed':True,'roles':['admin'],'groups':['membres']}
            for role in [Role.MEMBER,Role.VERIFIER,Role.ADMIN,Role.MEMBER]:
                user.role=role
                self.assertEqual(c.get('/api/test-role').json['role'],role.value)
                if role==Role.MEMBER:self.assertEqual(c.get('/api/verify').status_code,403)
            user.role=Role.ATTENTE
            self.assertEqual(c.get('/api/test-role').status_code,401)
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

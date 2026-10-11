"""Synthetic DEV/PG18 integration; no real identity or external payment/mail."""
import os,time,json,hmac,hashlib,uuid,unittest
from datetime import datetime,timedelta
from unittest.mock import patch
from types import SimpleNamespace
import psycopg
from sqlalchemy import text
from app import create_app
from app.models import db,User,Role,Membership,PendingRegistration,DevIdentityBinding,CardPaymentSettings
from app.card_payment import DEMO_IBAN,epc_payload,settings
from app.routes_memberships import _qr_serializer,current_academic_year
from app.dev_registration import ISSUER
ORIGIN='https://carte-dev.fede.fpms.ac.be'

class DevFlows(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  assert os.environ.get('DATABASE_URL','').startswith('postgresql+psycopg://postgres:postgres@127.0.0.1:15432/')
  with psycopg.connect('postgresql://postgres:postgres@127.0.0.1:15432/carte_fede_ci',autocommit=True) as c:
   if not c.execute("SELECT 1 FROM pg_roles WHERE rolname='carte_fede_dev'").fetchone():c.execute("CREATE ROLE carte_fede_dev LOGIN PASSWORD 'synthetic-test-only'")
   if not c.execute("SELECT 1 FROM pg_database WHERE datname='carte_fede_dev'").fetchone():c.execute("CREATE DATABASE carte_fede_dev OWNER carte_fede_dev")
  cls.environment=patch.dict(os.environ,dict(APP_ENV='development',AUTH_MODE='oidc',DEV_DATA_MODE='production_copy',DEV_REGISTRATION_ENABLED='1',DATABASE_URL='postgresql+psycopg://carte_fede_dev:synthetic-test-only@127.0.0.1:15432/carte_fede_dev',SECRET_KEY='synthetic-dev-key',AUTO_CREATE_DB='0',FRONTEND_BASE_URL=ORIGIN,OIDC_ISSUER_URL=ISSUER,OIDC_CLIENT_ID='carte-fede-dev',OIDC_CLIENT_SECRET='synthetic',OIDC_IDENTITY_BINDINGS=json.dumps({r:str(uuid.uuid5(uuid.NAMESPACE_URL,'synthetic/'+r)) for r in ['admin','verifier','member']}),DEV_IDENTITY_API_TOKEN='synthetic-api',DEV_ENROLLMENT_HOOK_KEY='synthetic-hook',DEV_DEFAULT_GROUP='default-group',DEV_MEMBERS_GROUP='members-group'))
  cls.environment.start();cls.app=create_app()
  from flask import g
  def clear_fixture_context():g.pop('_login_user',None)
  cls.app.before_request_funcs[None].insert(0,clear_fixture_context)
 @classmethod
 def tearDownClass(cls):cls.environment.stop()
 def setUp(self):
  self.context=self.app.app_context();self.context.push();db.drop_all();db.create_all();self.ids={}
  for r in ['admin','verifier','member']:
   uid=str(uuid.uuid5(uuid.NAMESPACE_URL,'synthetic/'+r));self.ids[r]=uid
   db.session.add(User(id=uid,nom='Synthetic',prenom=r,email=r+'@example.invalid',password_hash='!oidc-only',role=Role[r.upper()]))
  db.session.add(CardPaymentSettings(id=1,beneficiary='Copied setting never shown',iban='GB82WEST12345698765432',bic='WESTGB2L',amount=90,communication_prefix='Copied'))
  db.session.add(Membership(user_id=self.ids['member'],annee=2023,annee_code='A-TEST'));db.session.commit()
  self.patch=patch('app.oidc_dev.requests.get',side_effect=self.userinfo);self.patch.start()
 def tearDown(self):self.patch.stop();db.session.remove();self.context.pop()
 def userinfo(self,*a,**kw):
  sub=kw['headers']['Authorization'].split()[-1]
  return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'sub':sub,'carte_fede_uuid':self.ids.get(sub,''),'carte_fede_dev_allowed':True,'roles':['admin'],'groups':['superusers']})
 def client(self,role):
  c=self.app.test_client()
  with c.session_transaction() as s:s.update(_user_id=self.ids[role],_fresh=True,oidc_sub=role,oidc_access_token=role,oidc_expires_at=time.time()+300)
  return c
 def business(self,n='800001'):return dict(nom='Synthetic',prenom='Signup',member_id=n)
 def hook(self,sub,pk=1,operation='created',business=None,signature=True):
  raw=json.dumps(dict(operation=operation,subject=sub,auth_user_pk=pk,business=business or self.business())).encode();stamp=str(int(time.time()));sign=hmac.new(b'synthetic-hook',stamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
  return self.app.test_client().post('/api/dev/enrollment-hook',data=raw,headers={'Content-Type':'application/json','X-Enrollment-Time':stamp,'X-Enrollment-Signature':sign if signature else 'forged'})
 def native(self,sub,active=False):return dict(uuid=sub,path='users/carte-fede-dev-enrollment',type='internal',is_active=active,is_superuser=False,roles=[],groups=['default-group'],attributes={'carte_fede_dev_owned':True})
 def approve(self,request_id):return self.client('admin').post('/api/admin/registrations/'+request_id+'/approve',json={'add_card':True,'annee':current_academic_year()},headers={'Origin':ORIGIN})
 def test_settings_permissions_demo_only_and_origin(self):
  payload=dict(beneficiary='TEST DEMO',iban=DEMO_IBAN,bic='',amount='12.50',communication_prefix='TEST Carte')
  admin=self.client('admin');self.assertEqual(admin.get('/api/admin/card-payment').status_code,200);self.assertEqual(admin.get('/api/admin/card-payment').json['iban'],DEMO_IBAN)
  self.assertEqual(admin.put('/api/admin/card-payment',json=payload,headers={'Origin':'https://evil.invalid'}).status_code,403)
  self.assertEqual(admin.put('/api/admin/card-payment',json=payload,headers={'Origin':ORIGIN}).status_code,200)
  self.assertEqual(admin.patch('/api/admin/card-payment',json={'amount':'3.75'},headers={'Origin':ORIGIN}).status_code,200)
  self.assertEqual(self.app.test_client().get('/api/card-payment').json['iban'],DEMO_IBAN)
  for role in ['member','verifier']:self.assertEqual(self.client(role).put('/api/admin/card-payment',json=payload,headers={'Origin':ORIGIN}).status_code,403)
  self.assertEqual(admin.put('/api/admin/card-payment',json=dict(payload,iban='GB82WEST12345698765432'),headers={'Origin':ORIGIN}).status_code,400)
  self.assertEqual(str(db.session.get(CardPaymentSettings,1).amount),'90.00')
 def test_epc_preview_card_qr_and_signature_expiry(self):
  c=self.client('member');p=c.post('/api/card-payment/qr',json={'nom':'Synthetic','prenom':'QR'},headers={'Origin':ORIGIN});self.assertEqual(p.status_code,200);self.assertTrue(p.data.startswith(b'\x89PNG'))
  payload=epc_payload(settings(),'TEST DEMO');self.assertIn(DEMO_IBAN,payload);self.assertIn('BCD\n002\n1\nSCT',payload)
  self.assertEqual(c.get('/api/qr/2023.png').status_code,200)
  token=_qr_serializer().dumps({'uid':self.ids['member'],'annee':2023,'annee_code':'A-TEST','environment':'development'})
  verifier=self.client('verifier');self.assertTrue(verifier.get('/api/verify?token='+token).json['valid']);self.assertEqual(c.get('/api/verify?token='+token).status_code,403)
  self.assertEqual(verifier.get('/api/verify?token='+token+'forged').status_code,400)
  from itsdangerous import URLSafeTimedSerializer
  with self.assertRaises(Exception):URLSafeTimedSerializer('synthetic-prod-key',salt='qr-token-v1').loads(token)
  with patch('itsdangerous.timed.TimestampSigner.get_timestamp',return_value=int(time.time())-401*86400):expired=_qr_serializer().dumps({'uid':self.ids['member'],'annee':2023,'annee_code':'A-TEST','environment':'development'})
  self.assertEqual(verifier.get('/api/verify?token='+expired).status_code,400)
 def test_enrollment_approval_idempotency_and_api_retry(self):
  sub=str(uuid.uuid4());native=self.native(sub)
  with patch('app.dev_registration.api_user',return_value=native):
   self.assertEqual(self.hook(sub).status_code,202);self.assertEqual(self.hook(sub).status_code,202)
  b=db.session.get(DevIdentityBinding,(ISSUER,sub));request_id=b.pending_id;self.assertEqual(b.state,'pending')
  with patch('app.dev_registration.api_user',side_effect=__import__('requests').ConnectionError):self.assertEqual(self.approve(request_id).status_code,503)
  db.session.expire_all();b=db.session.get(DevIdentityBinding,(ISSUER,sub));self.assertEqual(b.state,'activating');self.assertEqual(db.session.get(User,b.user_id).role,Role.ATTENTE)
  def api(pk,patch=None):
   if patch:native.update(patch)
   return native
  with patch('app.dev_registration.api_user',side_effect=api):self.assertEqual(self.approve(request_id).status_code,200)
  self.assertEqual(self.approve(request_id).status_code,200);self.assertEqual(db.session.get(User,b.user_id).role,Role.MEMBER);self.assertEqual(Membership.query.filter_by(user_id=b.user_id).count(),1)
 def test_existing_active_identity_no_api_mutation_and_rejection(self):
  sub=str(uuid.uuid4());c=self.app.test_client()
  with c.session_transaction() as s:s.update(registration_subject=sub,registration_token=sub,registration_expires=time.time()+300)
  with patch('app.dev_registration.api_user') as api:
   self.assertEqual(c.post('/api/dev/registration',json=self.business(),headers={'Origin':ORIGIN}).status_code,202)
   b=db.session.get(DevIdentityBinding,(ISSUER,sub));self.assertEqual(self.approve(b.pending_id).status_code,200);api.assert_not_called()
  sub2=str(uuid.uuid4());native=self.native(sub2)
  with patch('app.dev_registration.api_user',return_value=native):self.assertEqual(self.hook(sub2,business=self.business('800002')).status_code,202)
  b2=db.session.get(DevIdentityBinding,(ISSUER,sub2));rid=b2.pending_id
  response=self.client('admin').post('/api/admin/registrations/'+rid+'/reject',json={},headers={'Origin':ORIGIN});self.assertEqual(response.status_code,200);self.assertEqual(db.session.get(DevIdentityBinding,(ISSUER,sub2)).state,'rejected')
 def test_collisions_wrong_attestation_historical_and_local_password_refusal(self):
  sub=str(uuid.uuid4());self.assertEqual(self.hook(sub,signature=False).status_code,401)
  self.assertEqual(self.client('member').post('/api/admin/users',json={'password':'must-not-hash'},headers={'Origin':ORIGIN}).status_code,403)
  with patch('app.routes_admin.generate_password_hash') as hash_password:
   self.assertEqual(self.client('admin').post('/api/admin/users',json={'password':'must-not-hash'},headers={'Origin':ORIGIN}).status_code,409);hash_password.assert_not_called()
  native=self.native(sub)
  with patch('app.dev_registration.api_user',return_value=native):
   self.assertEqual(self.hook(sub).status_code,202);self.assertEqual(self.hook(str(uuid.uuid4())).status_code,409)
  row=PendingRegistration(id=str(uuid.uuid4()),nom='Historical',prenom='Pending',member_id='800003',password_hash='copied-unusable-test',expires_at=datetime.utcnow()+timedelta(days=1));db.session.add(row);db.session.flush();db.session.add(DevIdentityBinding(issuer=ISSUER,subject=str(uuid.uuid4()),pending_id=row.id,request_id=row.id,state='historical',managed=False));db.session.commit()
  with patch('app.dev_registration.api_user') as api:self.assertEqual(self.approve(row.id).status_code,409);api.assert_not_called()

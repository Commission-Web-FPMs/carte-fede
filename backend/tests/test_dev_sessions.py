import os,time,unittest
from unittest.mock import patch
from types import SimpleNamespace
import requests
from app import create_app
from app.models import Role
import test_oidc_dev as oidc_tests

class DEVSessionTiming(unittest.TestCase):
 def setUp(self):
  self.start=time.time();self.clock=patch('app.oidc_dev.time.time',return_value=self.start);self.now=self.clock.start();self.addCleanup(self.clock.stop)
  helper=oidc_tests.OIDCSecurity();helper.setUp();self.env=helper.dev_env()
  with patch.dict(os.environ,self.env):self.app=create_app()
  self.client=self.app.test_client()
  with self.client.session_transaction() as s:s.update(oidc_sub='synthetic-sub',oidc_access_token='synthetic-access',oidc_refresh_token='synthetic-refresh',oidc_expires_at=self.start+300,oidc_created_at=self.start,oidc_last_activity=self.start,activity_csrf='synthetic-csrf')
  self.user=SimpleNamespace(is_authenticated=True,id='synthetic-business-uuid',role=Role.MEMBER)
  for target,name in [('app.oidc_dev.current_user','user_mock'),('app.oidc_dev.requests.get','get'),('app.oidc_dev.requests.post','post')]:
   p=patch(target,self.user) if name=='user_mock' else patch(target);setattr(self,name,p.start());self.addCleanup(p.stop)
  self.get.return_value.json.return_value={'sub':'synthetic-sub','carte_fede_uuid':'synthetic-business-uuid','carte_fede_dev_allowed':True}
  self.post.return_value.json.return_value={'access_token':'synthetic-renewed','refresh_token':'synthetic-rotated','expires_in':300,'token_type':'Bearer'}
  self.origin={'Origin':'https://carte-dev.fede.fpms.ac.be','X-Session-Activity-CSRF':'synthetic-csrf'}
 def activity(self):return self.client.post('/api/auth/session/activity',headers=self.origin)
 def test_defaults_and_verified_password_target(self):
  self.assertEqual(self.app.config['DEV_SESSION_IDLE_SECONDS'],1800);self.assertEqual(self.app.config['DEV_SESSION_ABSOLUTE_SECONDS'],28800)
  self.assertTrue(self.app.config['SESSION_COOKIE_HTTPONLY']);self.assertTrue(self.app.config['SESSION_COOKIE_SECURE']);self.assertEqual(self.app.config['SESSION_COOKIE_SAMESITE'],'Lax')
  self.assertEqual(self.client.get('/api/auth/mode').json['password_change_url'],'https://auth.fede.fpms.ac.be/if/flow/default-password-change/')
  for key,val in [('DEV_SESSION_IDLE_SECONDS','899'),('DEV_SESSION_ABSOLUTE_SECONDS','1200'),('OIDC_PASSWORD_CHANGE_URL','https://evil.invalid/')]:
   with patch.dict(os.environ,dict(self.env,**{key:val})),self.assertRaises(RuntimeError):create_app()
 def test_activity_survives_fifteen_minutes_and_rotates_tokens(self):
  for minute in range(4,45,4):self.now.return_value=self.start+minute*60;self.assertEqual(self.activity().status_code,200)
  with self.client.session_transaction() as s:self.assertEqual(s['oidc_last_activity'],self.start+44*60);self.assertEqual(s['oidc_created_at'],self.start);self.assertEqual(s['oidc_refresh_token'],'synthetic-rotated')
  self.assertTrue(any(c.kwargs.get('data',{}).get('grant_type')=='refresh_token' for c in self.post.call_args_list))
 def test_polling_and_refresh_never_slide_deadline(self):
  for minute in [4,8,16,29]:self.now.return_value=self.start+minute*60;self.assertEqual(self.client.get('/api/auth/session').status_code,200)
  with self.client.session_transaction() as s:self.assertEqual(s['oidc_last_activity'],self.start)
  self.now.return_value=self.start+1800;self.assertEqual(self.client.get('/api/auth/session').status_code,401);self.assertEqual(self.activity().status_code,401)
 def test_health_and_mode_do_not_count_as_activity(self):
  self.now.return_value=self.start+2000;self.client.get('/api/health');self.client.get('/api/auth/mode')
  with self.client.session_transaction() as s:self.assertEqual(s['oidc_last_activity'],self.start)
  self.assertEqual(self.activity().status_code,401)
 def test_absolute_expiry_even_with_recent_activity(self):
  with self.client.session_transaction() as s:s['oidc_last_activity']=self.start+28790
  self.now.return_value=self.start+28800;self.assertEqual(self.activity().status_code,401)
 def test_activity_requires_origin_and_csrf(self):
  self.now.return_value=self.start+60
  for headers in [{},{'Origin':'https://evil.invalid','X-Session-Activity-CSRF':'synthetic-csrf'},{'Origin':self.origin['Origin'],'X-Session-Activity-CSRF':'wrong'}]:self.assertEqual(self.client.post('/api/auth/session/activity',headers=headers).status_code,403)
  with self.client.session_transaction() as s:self.assertEqual(s['oidc_last_activity'],self.start)
 def test_disabled_unapproved_or_wrong_mapping_revokes(self):
  for bad in [{'carte_fede_dev_allowed':False},{'sub':'other'},{'carte_fede_uuid':'other'}]:
   with self.client.session_transaction() as s:s.update(oidc_created_at=self.start,oidc_last_activity=self.start,oidc_access_token='synthetic-access',oidc_expires_at=self.start+300,oidc_sub='synthetic-sub')
   self.get.return_value.json.return_value={'sub':'synthetic-sub','carte_fede_uuid':'synthetic-business-uuid','carte_fede_dev_allowed':True}|bad
   self.assertEqual(self.activity().status_code,401)
 def test_refresh_rejection_and_logout_clear_tokens(self):
  self.now.return_value=self.start+300;self.post.return_value.raise_for_status.side_effect=requests.HTTPError();self.assertEqual(self.activity().status_code,401)
  with self.client.session_transaction() as s:self.assertNotIn('oidc_access_token',s);self.assertNotIn('oidc_refresh_token',s)
  self.post.return_value.raise_for_status.side_effect=None
  with self.client.session_transaction() as s:s.update(oidc_sub='synthetic-sub',oidc_access_token='synthetic-access',oidc_refresh_token='synthetic-refresh',oidc_expires_at=self.start+600,oidc_created_at=self.start,oidc_last_activity=self.start)
  self.assertEqual(self.client.post('/api/auth/logout',headers={'Origin':self.origin['Origin']}).status_code,200)
  with self.client.session_transaction() as s:self.assertNotIn('oidc_access_token',s);self.assertNotIn('oidc_refresh_token',s)

 def test_expiry_redirect_requires_native_reauthentication(self):
  from urllib.parse import urlsplit,parse_qs
  self.user.is_authenticated=False
  r=self.client.get('/api/auth/oidc/login?expired=1')
  q=parse_qs(urlsplit(r.location).query)
  self.assertEqual(q['prompt'],['login']);self.assertEqual(q['max_age'],['0']);self.assertIn('offline_access',q['scope'][0])

 def test_same_cookie_concurrent_refresh_is_serialized(self):
  from concurrent.futures import ThreadPoolExecutor
  self.now.return_value=self.start+300
  cookie=self.client.get_cookie('__Host-carte-fede-dev')
  import threading
  ready=threading.Barrier(2)
  response=self.post.return_value
  def delayed_post(*args,**kwargs):time.sleep(0.1);return response
  self.post.side_effect=delayed_post
  def call():
   client=self.app.test_client();client.set_cookie(cookie.key,cookie.value);ready.wait(timeout=5)
   return client.get('/api/auth/session').status_code
  with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(list(pool.map(lambda _:call(),range(2))),[200,200])
  refreshes=[c for c in self.post.call_args_list if c.kwargs.get('data',{}).get('grant_type')=='refresh_token']
  self.assertEqual(len(refreshes),1)

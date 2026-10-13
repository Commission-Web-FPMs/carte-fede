"""Automatic accounts on disposable lab PG18; no real email or identity calls."""
import os,uuid,unittest
from unittest.mock import patch
import test_dev_flows as fixtures
from app.models import db,User,Role,Membership,PendingCardRequest,DevIdentityBinding
from app.dev_registration import automatic_enrollment,RegistrationError,ISSUER


class AutomaticAccounts(unittest.TestCase):
    setUpClass=fixtures.DevFlows.__dict__['setUpClass']
    tearDownClass=fixtures.DevFlows.__dict__['tearDownClass']
    userinfo=fixtures.DevFlows.userinfo
    client=fixtures.DevFlows.client
    def setUp(self):
        fixtures.DevFlows.setUp(self)
        self.flag=patch.dict(os.environ,DEV_EMAIL_REGISTRATION_ENABLED='1');self.flag.start()
        self.sub=str(uuid.uuid4())
        self.event=dict(operation='email-created',subject=self.sub,auth_user_pk=10,
                        business=dict(nom='Synthetic',prenom='Automatic',identifier='990801'))
        self.native=dict(uuid=self.sub,email='990801@umons.ac.be',type='internal',
                         path='users/carte-fede-dev-enrollment',is_active=False,
                         is_superuser=False,roles=[],groups=['default-group'],
                         attributes={'carte_fede_dev_owned':True})
    def tearDown(self):
        self.flag.stop();fixtures.DevFlows.tearDown(self)
    def api(self,pk,patch=None):
        if patch:self.native.update(patch)
        return self.native
    def reserve(self):
        with patch('app.dev_registration.api_user',side_effect=self.api):
            return automatic_enrollment(self.event)
    def proof(self):
        self.native['attributes'].update(carte_fede_dev_verified_email=self.native['email'],
            carte_fede_dev_email_proof='p'*32,carte_fede_dev_password_initialized=True)
        self.event.update(operation='email-verified',proof_id='p'*32)
    def test_no_access_no_card_before_proof_and_admin_cannot_activate(self):
        self.reserve();b=db.session.get(DevIdentityBinding,(ISSUER,self.sub))
        self.assertEqual(b.state,'email_pending');self.assertIsNone(b.user_id)
        self.assertEqual(User.query.count(),3)
        self.event['operation']='email-verified'
        with patch('app.dev_registration.api_user',side_effect=self.api),self.assertRaises(RegistrationError):
            automatic_enrollment(self.event)
        db.session.rollback()
        c=self.client('admin')
        self.assertEqual(c.post('/api/admin/registrations/'+b.request_id+'/approve',json={},
            headers={'Origin':'https://carte-dev.fede.fpms.ac.be'}).status_code,409)
        self.assertFalse(self.native['is_active'])
    def test_automatic_member_is_idempotent_without_card_or_request(self):
        self.reserve();self.proof()
        with patch('app.dev_registration.api_user',side_effect=self.api):
            a=automatic_enrollment(self.event);b=automatic_enrollment(self.event)
        self.assertEqual(a,b);self.assertEqual(db.session.get(User,a['user_id']).role,Role.MEMBER)
        self.assertTrue(self.native['is_active']);self.assertIn('members-group',self.native['groups'])
        self.assertEqual(Membership.query.filter_by(user_id=a['user_id']).count(),0)
        self.assertEqual(PendingCardRequest.query.filter_by(user_id=a['user_id']).count(),0)
        self.assertEqual(User.query.count(),4)
    def test_remote_failure_retains_attente_and_same_uuid_on_resume(self):
        self.reserve();self.proof()
        def failing(pk,patch=None):
            if patch:raise RegistrationError('synthetic outage',503)
            return self.native
        with patch('app.dev_registration.api_user',side_effect=failing),self.assertRaises(RegistrationError):
            automatic_enrollment(self.event)
        db.session.rollback();b=db.session.get(DevIdentityBinding,(ISSUER,self.sub))
        uid=b.user_id;self.assertEqual(b.state,'provisioning')
        self.assertEqual(db.session.get(User,uid).role,Role.ATTENTE)
        with patch('app.dev_registration.api_user',side_effect=self.api):result=automatic_enrollment(self.event)
        self.assertEqual(result['user_id'],uid);self.assertEqual(User.query.count(),4)
    def test_existing_identity_local_only_and_no_email_adoption(self):
        self.event.update(operation='existing-verified',active_attestation=True)
        with patch('app.dev_registration.api_user') as api:
            result=automatic_enrollment(self.event);api.assert_not_called()
        self.assertEqual(db.session.get(User,result['user_id']).role,Role.MEMBER)
        self.assertEqual(PendingCardRequest.query.count(),0)
        self.event['subject']=str(uuid.uuid4())
        with self.assertRaises(RegistrationError):automatic_enrollment(self.event)
        db.session.rollback();self.assertEqual(User.query.count(),4)
    def test_historical_binding_cannot_be_promoted(self):
        from app.models import PendingRegistration
        from datetime import datetime,timedelta
        row=PendingRegistration(id=str(uuid.uuid4()),nom='Synthetic',prenom='Historical',member_id='990801',password_hash='!historical-unusable',expires_at=datetime.utcnow()+timedelta(days=1))
        db.session.add(row);db.session.flush()
        b=DevIdentityBinding(issuer=ISSUER,subject=self.sub,pending_id=row.id,request_id=row.id,state='historical',managed=False)
        db.session.add(b);db.session.commit()
        self.event.update(operation='existing-verified',active_attestation=True)
        with self.assertRaises(RegistrationError):automatic_enrollment(self.event)
        db.session.rollback();self.assertEqual(b.state,'historical')
        self.assertEqual(User.query.count(),3);self.assertIsNotNone(db.session.get(PendingRegistration,row.id))
    def test_authoritative_existing_admin_uuid_and_role_preserved(self):
        import json
        self.event.update(operation='existing-verified',active_attestation=True)
        with patch.dict(os.environ,OIDC_IDENTITY_BINDINGS=json.dumps({self.sub:self.ids['admin']})),patch('app.dev_registration.api_user') as api:
            result=automatic_enrollment(self.event);api.assert_not_called()
        self.assertEqual(result['user_id'],self.ids['admin'])
        self.assertEqual(db.session.get(User,self.ids['admin']).role,Role.ADMIN)
        self.assertEqual(User.query.count(),3);self.assertEqual(DevIdentityBinding.query.count(),0)

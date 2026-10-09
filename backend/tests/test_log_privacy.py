"""Only synthetic sentinels; no production database or accounts are used."""
import io, json, logging, os, unittest
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy.exc import StatementError
from psycopg.errors import UniqueViolation
from app import create_app
from app.models import db
from app.safe_logging import PrivacyFormatter

SENTINELS = ['private-mail@example.invalid','PRIVATE_PASSWORD_123','PRIVATE_QR_TOKEN_123','PRIVATE_COOKIE_123','PRIVATE_NAME_123','PRIVATE_HASH_123']
PAYLOAD = ' '.join(SENTINELS)

class LogPrivacyTest(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'DATABASE_URL':'sqlite://','SECRET_KEY':'synthetic-test-key','AUTO_CREATE_DB':'0','FRONTEND_BASE_URL':'https://synthetic.invalid'})
        self.environment.start()
        self.app = create_app()
        self.app.config.update(TESTING=False,PROPAGATE_EXCEPTIONS=False)
        self.stream=io.StringIO()
        self.handler=logging.StreamHandler(self.stream)
        self.handler.setFormatter(PrivacyFormatter())
        self.app.logger.addHandler(self.handler)
    def tearDown(self):
        self.app.logger.removeHandler(self.handler)
        self.environment.stop()
    def safe_output(self):
        output=self.stream.getvalue()
        for marker in SENTINELS: self.assertNotIn(marker,output)
        return [json.loads(line) for line in output.splitlines() if line]
    def test_login_sql_error_hides_statement_parameters_and_driver_detail(self):
        driver=UniqueViolation(PAYLOAD)
        error=StatementError('query failed '+PAYLOAD,"SELECT '"+PAYLOAD+"'",{'password':PAYLOAD},driver)
        with patch('app.routes_auth.User') as user:
            user.query.filter_by.side_effect=error
            response=self.app.test_client().post('/api/auth/login',json={'email':SENTINELS[0],'password':SENTINELS[1]})
        self.assertEqual(response.status_code,500)
        record=self.safe_output()[-1]
        self.assertEqual(record['event'],'login_failed');self.assertEqual(record['sqlstate'],'23505');self.assertTrue(record['frames'])
    def test_unhandled_error_hides_message_and_request_target(self):
        @self.app.get('/synthetic/<value>')
        def fail(value): raise RuntimeError(PAYLOAD)
        response=self.app.test_client().get('/synthetic/'+SENTINELS[2],headers={'Cookie':'session='+SENTINELS[3]},query_string={'token':SENTINELS[2]})
        self.assertEqual(response.status_code,500)
        record=self.safe_output()[-1]
        self.assertEqual(record['event'],'unhandled_request_error');self.assertEqual(record['category'],'RuntimeError')
    def test_smtp_failure_hides_recipient_body_reset_token_and_password(self):
        user=SimpleNamespace(prenom=SENTINELS[4],email=SENTINELS[0],member_id=None)
        with patch('app.routes_auth.User') as users, patch('app.routes_auth.generate_reset_token',return_value=SENTINELS[2]), patch('app.routes_auth.send_email',side_effect=RuntimeError(PAYLOAD)):
            users.query.filter_by.return_value.first.return_value=user
            response=self.app.test_client().post('/api/auth/request-password-reset',json={'email':SENTINELS[0]})
        self.assertEqual(response.status_code,200);self.assertEqual(self.safe_output()[-1]['event'],'password_reset_email_failed')
    def test_generic_driver_and_gunicorn_errors_ignore_all_message_arguments(self):
        for name in ['psycopg','sqlalchemy.engine','gunicorn.error']:
            record=logging.LogRecord(name,logging.ERROR,__file__,1,'Error handling request %s',(PAYLOAD,),None)
            output=PrivacyFormatter().format(record)
            for marker in SENTINELS: self.assertNotIn(marker,output)
    def test_access_logging_ignores_url_cookie_authorization_and_custom_method(self):
        atoms={'m':'GET','s':'200','L':'0.002','r':PAYLOAD,'U':PAYLOAD,'q':PAYLOAD,'{cookie}i':PAYLOAD,'{authorization}i':PAYLOAD}
        record=logging.LogRecord('gunicorn.access',logging.INFO,__file__,1,'%(r)s',(atoms,),None)
        output=PrivacyFormatter().format(record)
        for marker in SENTINELS: self.assertNotIn(marker,output)
        parsed=json.loads(output);self.assertEqual(parsed['method'],'GET');self.assertEqual(parsed['status'],'200')
        record.args['m']=PAYLOAD;self.assertEqual(json.loads(PrivacyFormatter().format(record))['method'],'OTHER')
    def test_engine_is_quiet_and_hides_parameters(self):
        with self.app.app_context(): self.assertTrue(db.engine.hide_parameters);self.assertFalse(db.engine.echo)

if __name__=='__main__': unittest.main()

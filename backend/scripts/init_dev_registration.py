"""Add only DEV identity journal; preserve every copied business row."""
import json,os,sys,uuid
from pathlib import Path
from sqlalchemy.engine import make_url
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
u=make_url(os.environ['DATABASE_URL'])
assert os.environ.get('APP_ENV')=='development' and os.environ.get('AUTH_MODE')=='oidc' and u.username==u.database=='carte_fede_dev'
from app import create_app
from app.models import db,User,PendingRegistration,DevIdentityBinding
from app.dev_registration import ISSUER
app=create_app()
with app.app_context():
 from sqlalchemy import text
 assert db.session.execute(text('select current_database(),current_user')).one()==('carte_fede_dev','carte_fede_dev')
 DevIdentityBinding.__table__.create(db.engine,checkfirst=True)
 for subject,user_id in json.loads(os.environ['OIDC_IDENTITY_BINDINGS']).items():
  assert db.session.get(User,user_id)
  old=db.session.get(DevIdentityBinding,(ISSUER,subject))
  if old:assert old.user_id==user_id and old.state=='approved'
  else:db.session.add(DevIdentityBinding(issuer=ISSUER,subject=subject,user_id=user_id,request_id=str(uuid.uuid5(uuid.NAMESPACE_URL,ISSUER+subject)),managed=False,state='approved'))
 for binding in json.loads(os.environ['DEV_HISTORICAL_BINDINGS']):
  assert db.session.get(PendingRegistration,binding['pending_id'])
  old=db.session.get(DevIdentityBinding,(ISSUER,binding['subject']))
  if old:assert old.state=='historical' and old.pending_id==binding['pending_id']
  else:db.session.add(DevIdentityBinding(issuer=ISSUER,subject=binding['subject'],pending_id=binding['pending_id'],request_id=binding['pending_id'],managed=False,state='historical'))
 db.session.commit()
 print('SAFE_DEV_REGISTRATION_SCHEMA identity_journal_initialized_existing_business_rows_unchanged')

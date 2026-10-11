"""Create/reinitialize synthetic DEV fixtures; never use a production connection."""
import argparse, os, sys, uuid
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy.engine import make_url
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
u=make_url(os.environ["DATABASE_URL"])
assert os.environ.get("APP_ENV")=="development" and u.database=="carte_fede_dev" and u.username=="carte_fede_dev", "DEV database/role required before SQL"
from app import create_app
from app.models import db, User, Role, Membership, PendingRegistration, CardPaymentSettings
p=argparse.ArgumentParser();p.add_argument("--reset-synthetic-dev",action="store_true");a=p.parse_args()
app=create_app()
with app.app_context():
    with db.engine.connect() as c:
        from sqlalchemy import text
        assert c.execute(text("select current_database(), current_user")).one()==("carte_fede_dev","carte_fede_dev")
    if a.reset_synthetic_dev:
        db.drop_all()
    db.create_all()
    for i, label in enumerate(["admin","verifier","member","attente"],1):
        uid=str(uuid.uuid5(uuid.NAMESPACE_URL,"carte-fede-dev/"+label))
        if not db.session.get(User,uid):
            db.session.add(User(id=uid,nom="Synthétique",prenom=label,member_id="90000"+str(i),email=None,password_hash="!disabled-local-auth",role=Role[label.upper()]))
    db.session.flush()
    for i,label in enumerate(["admin","verifier","member"],1):
        uid=str(uuid.uuid5(uuid.NAMESPACE_URL,"carte-fede-dev/"+label))
        mid=str(uuid.uuid5(uuid.NAMESPACE_URL,"carte-fede-dev/card/"+label))
        if not db.session.get(Membership,mid):db.session.add(Membership(id=mid,user_id=uid,annee=2026,annee_code="DEV-"+str(i)))
    pid=str(uuid.uuid5(uuid.NAMESPACE_URL,"carte-fede-dev/pending"))
    if not db.session.get(PendingRegistration,pid):db.session.add(PendingRegistration(id=pid,nom="Synthétique",prenom="pending",member_id="900005",email=None,password_hash="!disabled-local-auth",expires_at=datetime.utcnow()+timedelta(days=3650)))
    if not db.session.get(CardPaymentSettings,1):db.session.add(CardPaymentSettings(id=1,beneficiary="DEV — aucun paiement",iban="",bic="",amount=None,communication_prefix="SYNTHETIQUE"))
    db.session.commit()
    print("Synthetic DEV schema/fixtures ready; emails and payments disabled")

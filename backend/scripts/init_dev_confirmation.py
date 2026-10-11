"""Add only the DEV single-use confirmation table; never alter copied tables."""
import os, sys
from pathlib import Path
from sqlalchemy.engine import make_url
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
url = make_url(os.environ['DATABASE_URL'])
assert os.environ.get('APP_ENV') == 'development' and os.environ.get('AUTH_MODE') == 'oidc'
assert url.username == url.database == 'carte_fede_dev'
from app import create_app
from app.models import db, DevEnrollmentConfirmation
from sqlalchemy import text
app = create_app()
with app.app_context():
    assert db.session.execute(text('select current_database(),current_user')).one() == ('carte_fede_dev', 'carte_fede_dev')
    DevEnrollmentConfirmation.__table__.create(db.engine, checkfirst=True)
    print('SAFE_DEV_CONFIRMATION_TABLE_READY copied_business_tables_unchanged')

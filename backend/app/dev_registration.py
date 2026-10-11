"""DEV-only approval journal. Identity verified by OIDC or signed native enrollment."""
import hashlib, hmac, json, os, re, time, uuid, secrets
from collections import deque
from threading import Lock
_enrollment_checks=deque()
_enrollment_lock=Lock()
from datetime import datetime, timedelta
import requests
from flask import Blueprint, current_app, jsonify, request, session, redirect
from itsdangerous import URLSafeTimedSerializer, BadSignature
from sqlalchemy.exc import IntegrityError
from .models import db, DevIdentityBinding, DevEnrollmentConfirmation, PendingRegistration, User, Role, Membership, PendingCardRequest

ISSUER = "https://auth.fede.fpms.ac.be/application/o/carte-fede-dev/"
ORIGIN = "https://carte-dev.fede.fpms.ac.be"
AUTH = "https://auth.fede.fpms.ac.be"
bp = Blueprint("dev_registration", __name__)

class RegistrationError(Exception):
    def __init__(self, message, status=409):
        self.message, self.status = message, status

def fail(error):
    db.session.rollback()
    return jsonify(error=error.message), error.status

def identity_binding(subject):
    if os.getenv("DEV_REGISTRATION_ENABLED") != "1":
        return None
    return db.session.get(DevIdentityBinding, (ISSUER, subject), populate_existing=True)

def bound_identity(subject):
    b = identity_binding(subject)
    return b.user_id if b and b.state == "approved" else None

def business_data(data):
    if not isinstance(data, dict) or any(k in data for k in ["password", "password2", "role", "groups", "user_id", "subject"]):
        raise RegistrationError("Données métier invalides ; aucun mot de passe local.", 400)
    keys = ["nom", "prenom", "member_id", "email"]
    if any(not isinstance(data.get(k, ""), str) for k in keys):
        raise RegistrationError("Informations métier invalides.", 400)
    values = {k: data.get(k, "").strip() for k in keys}
    values['email'] = values['email'].lower()
    if not values['nom'] or not values['prenom'] or max(len(values['nom']),len(values['prenom']))>100 or any(re.search(r'[\x00-\x1f\x7f]',v) for v in values.values()):
        raise RegistrationError("Nom et prénom requis, caractères de contrôle interdits.", 400)
    if bool(values['member_id']) == bool(values['email']):
        raise RegistrationError("Un seul identifiant métier requis.", 400)
    if values['member_id'] and not re.fullmatch(r'[0-9]{6}',values['member_id']):
        raise RegistrationError("Matricule de six chiffres requis.", 400)
    if values['email'] and (len(values['email'])>254 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',values['email'])):
        raise RegistrationError("Email invalide.", 400)
    if type(data.get('free_card_requested',False)) is not bool:
        raise RegistrationError("Option invalide.", 400)
    values['free_card_requested']=data.get('free_card_requested',False)
    return values

def check_available(values):
    for model in [User, PendingRegistration]:
        if (values['member_id'] and model.query.filter_by(member_id=values['member_id']).first()) or (values['email'] and model.query.filter(db.func.lower(model.email)==values['email']).first()):
            raise RegistrationError("Identifiant déjà utilisé ou en attente ; aucun rapprochement automatique.")

def create_pending(subject, data, managed=False, auth_pk=None, request_id=None):
    from .routes_memberships import current_academic_year
    subject=str(uuid.UUID(subject)); old=identity_binding(subject)
    if old:
        if old.state in ['pending','activating']:
            return old
        raise RegistrationError("Identité déjà associée ou demande déjà traitée.")
    values=business_data(data);check_available(values)
    row=PendingRegistration(id=str(uuid.uuid4()),nom=values['nom'],prenom=values['prenom'],member_id=values['member_id'] or None,email=values['email'] or None,password_hash='!oidc-only',expires_at=datetime.utcnow()+timedelta(days=30),free_card_requested=values['free_card_requested'],card_year=current_academic_year())
    b=DevIdentityBinding(issuer=ISSUER,subject=subject,pending_id=row.id,request_id=row.id,managed=managed,auth_user_pk=auth_pk,state='pending')
    db.session.add(row);db.session.flush();db.session.add(b);db.session.commit();return b

def api_user(pk, patch=None):
    if type(pk) is not int or pk<1:
        raise RegistrationError("Identité Authentik non vérifiée.")
    r=requests.request('PATCH' if patch is not None else 'GET',AUTH+'/api/v3/core/users/'+str(pk)+'/',headers={'Authorization':'Bearer '+os.environ['DEV_IDENTITY_API_TOKEN']},json=patch,timeout=8,allow_redirects=False)
    if r.status_code != 200:
        raise RegistrationError("Opération identité indisponible ; demande conservée, réessayez.",503)
    return r.json()

def verify_owned(b, u):
    allowed={os.environ['DEV_DEFAULT_GROUP'],os.environ['DEV_MEMBERS_GROUP']}
    if str(u.get('uuid')) != b.subject or u.get('path') != 'users/carte-fede-dev-enrollment' or u.get('type') != 'internal' or u.get('is_superuser') or u.get('roles') or not set(u.get('groups',[]))<=allowed or u.get('attributes',{}).get('carte_fede_dev_owned') is not True:
        raise RegistrationError("Identité hors périmètre DEV ; aucune modification autorisée.")
    expected=u.get('attributes',{}).get('carte_fede_dev_business_uuid')
    if expected and expected != b.user_id:
        raise RegistrationError("Association conflictuelle ; intervention opérateur requise.")

def decide(row, decision, data):
    from .routes_memberships import current_academic_year, ALLOWED_PREFIXES, next_available_card_code
    b=DevIdentityBinding.query.filter_by(pending_id=row.id).with_for_update().first()
    if not b:
        raise RegistrationError("Inscription historique sans association vérifiée ; intervention opérateur requise.")
    if b.state=='historical' and decision=='approve':
        raise RegistrationError("Activation de l’identité historique partagée : opération opérateur séparée.")
    if b.state not in ['pending','activating','historical']:
        raise RegistrationError("Demande déjà traitée.")
    if decision=='reject':
        if b.state=='activating':
            raise RegistrationError("Approbation commencée : terminer la reprise, ne pas désactiver une identité globale.")
        b.state='rejected';db.session.delete(row);db.session.commit();return {'ok':True,'state':'rejected'}
    if not isinstance(data,dict):raise RegistrationError('Données invalides.',400)
    add_card=data.get('add_card') is True;year=data.get('annee');prefix=str(data.get('prefix') or 'A').upper()
    if add_card and not (data.get('payment_confirmed') is True or (row.free_card_requested and data.get('bac1_verified') is True)):
        raise RegistrationError('Confirmez le paiement ou vérifiez explicitement l’exemption BAC1 avant attribution.')
    if add_card and (type(year) is not int or year not in [current_academic_year(),current_academic_year()+1] or prefix not in ALLOWED_PREFIXES):raise RegistrationError('Année/préfixe invalide.',400)
    # A persistent ATTENTE user is the local barrier between the two systems.
    if b.state=='pending':
        if (row.member_id and User.query.filter_by(member_id=row.member_id).first()) or (row.email and User.query.filter(db.func.lower(User.email)==row.email).first()):raise RegistrationError('Identifiant déjà utilisé.')
        user=User(id=str(uuid.uuid4()),nom=row.nom,prenom=row.prenom,member_id=row.member_id,email=row.email,password_hash='!oidc-only',role=Role.ATTENTE)
        db.session.add(user);db.session.flush();b.user_id=user.id;b.state='activating';db.session.commit()
    if b.managed:
        u=api_user(b.auth_user_pk);verify_owned(b,u)
        attrs=u.get('attributes',{}).copy();attrs['carte_fede_dev_business_uuid']=b.user_id
        groups=list(set(u.get('groups',[]))|{os.environ['DEV_MEMBERS_GROUP']})
        u=api_user(b.auth_user_pk,{'attributes':attrs,'groups':groups,'is_active':True});verify_owned(b,u)
        if not u.get('is_active') or os.environ['DEV_MEMBERS_GROUP'] not in u.get('groups',[]) or u['attributes'].get('carte_fede_dev_business_uuid') != b.user_id:raise RegistrationError('Activation non confirmée ; reprise requise.',503)
    # Existing identities are never patched: OIDC attestation and local binding suffice.
    # The durable activating commit released the first lock. Serialize finalization
    # again after the remote operation, including different-year approval retries.
    subject=b.subject
    db.session.expire_all()
    b=DevIdentityBinding.query.filter_by(issuer=ISSUER,subject=subject).populate_existing().with_for_update().one()
    if b.state=='approved':return {'ok':True,'user_id':b.user_id,'state':'approved'}
    if b.state!='activating':raise RegistrationError('État modifié ; intervention opérateur requise.')
    user=db.session.get(User,b.user_id);user.role=Role.MEMBER
    if add_card and not Membership.query.filter_by(user_id=user.id,annee=year).first():db.session.add(Membership(user_id=user.id,annee=year,annee_code=next_available_card_code(year,prefix)))
    elif not add_card and not PendingCardRequest.query.filter_by(user_id=user.id,annee=row.card_year or current_academic_year()).first():db.session.add(PendingCardRequest(user_id=user.id,annee=row.card_year or current_academic_year(),status='pending' if row.free_card_requested else 'payment_required',free_card=row.free_card_requested))
    b.state='approved';db.session.delete(row);db.session.commit();return {'ok':True,'user_id':user.id,'state':'approved'}

@bp.before_request
def registration_guard():
    if request.path in ['/api/dev/enrollment-confirm', '/api/dev/enrollment-notice']:
        return None
    if request.method not in ['GET','HEAD'] and request.path!='/api/dev/enrollment-hook' and request.headers.get('Origin')!=ORIGIN:return jsonify(error='invalid_origin'),403
    if request.path=='/api/dev/enrollment-hook':return None
    try:
        if time.time()>=session.get('registration_expires',0):raise RegistrationError('Authentification Authentik requise.',401)
        r=requests.get(AUTH+'/application/o/userinfo/',headers={'Authorization':'Bearer '+session['registration_token']},timeout=8,allow_redirects=False);r.raise_for_status();info=r.json()
        if info.get('sub')!=session.get('registration_subject') or info.get('carte_fede_dev_allowed') is not True:raise RegistrationError('Identité inactive ou session révoquée.',401)
    except (requests.RequestException,KeyError):return jsonify(error='registration_session_unavailable'),401
    except RegistrationError as e:return fail(e)

@bp.route('/api/dev/registration',methods=['GET','POST'])
def registration():
    try:
        sub=session['registration_subject']
        if request.method=='GET':
            b=identity_binding(sub);return jsonify(state=b.state if b else 'unregistered',authenticated=True)
        b=create_pending(sub,request.get_json(silent=True));return jsonify(ok=True,state=b.state,request_id=b.request_id),202
    except (RegistrationError,ValueError) as e:return fail(e if isinstance(e,RegistrationError) else RegistrationError('Identité invalide.',400))
    except IntegrityError:return fail(RegistrationError('Demande concurrente ou identifiant déjà utilisé.'))

@bp.post('/api/dev/enrollment-hook')
def enrollment_hook():
    try:
        raw=request.get_data(cache=True)
        if len(raw)>4096:raise RegistrationError('Données invalides.',400)
        stamp=request.headers.get('X-Enrollment-Time','');signature=request.headers.get('X-Enrollment-Signature','')
        key=os.environ['DEV_ENROLLMENT_HOOK_KEY'];expected=hmac.new(key.encode(),stamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
        if not stamp.isdigit() or abs(time.time()-int(stamp))>60 or not hmac.compare_digest(signature,expected):raise RegistrationError('Attestation invalide.',401)
        data=json.loads(raw);values=business_data(data.get('business'))
        if data.get('operation')=='check':
            with _enrollment_lock:
                now=time.time()
                while _enrollment_checks and _enrollment_checks[0]<now-3600:_enrollment_checks.popleft()
                if len(_enrollment_checks)>=20:raise RegistrationError('Trop de demandes ; réessayez plus tard.',429)
                _enrollment_checks.append(now)
            check_available(values);return jsonify(ok=True)
        if data.get('operation') not in ['created','existing']:raise RegistrationError('Opération invalide.',400)
        subject=str(uuid.UUID(data['subject']))
        managed=data['operation']=='created'
        if managed:
            u=api_user(data['auth_user_pk']);probe=DevIdentityBinding(subject=subject,user_id=None)
            verify_owned(probe,u)
            if u.get('is_active'):raise RegistrationError('Nouvelle identité doit être inactive.')
        elif data.get('active_attestation') is not True:
            raise RegistrationError('Identité active non attestée.',401)
        # Only native flow fields, never passwords, reach this API.
        b=create_pending(subject,values,managed=managed,auth_pk=data['auth_user_pk'] if managed else None,request_id=subject)
        nonce=secrets.token_urlsafe(32)
        db.session.add(DevEnrollmentConfirmation(nonce_digest=hashlib.sha256(nonce.encode()).hexdigest(),request_id=b.request_id,expires_at=datetime.utcnow()+timedelta(minutes=5)))
        db.session.commit()
        token=URLSafeTimedSerializer(current_app.config['SECRET_KEY'],salt='dev-enrollment-confirmation-v1').dumps({'nonce':nonce})
        return jsonify(ok=True,state=b.state,confirmation_url=ORIGIN+'/api/dev/enrollment-confirm?state='+token),202
    except RegistrationError as e:return fail(e)
    except (ValueError,KeyError,TypeError):return fail(RegistrationError('Attestation invalide.',400))
    except IntegrityError:return fail(RegistrationError('Conflit de demande.'))
    except requests.RequestException:return fail(RegistrationError('Identité indisponible ; aucune activation.',503))

@bp.get('/api/dev/enrollment-confirm')
def enrollment_confirm():
    try:
        payload=URLSafeTimedSerializer(current_app.config['SECRET_KEY'],salt='dev-enrollment-confirmation-v1').loads(request.args.get('state',''),max_age=300)
        digest=hashlib.sha256(payload['nonce'].encode()).hexdigest()
        row=DevEnrollmentConfirmation.query.filter_by(nonce_digest=digest).with_for_update().first()
        if not row or row.consumed_at or row.expires_at<=datetime.utcnow():raise ValueError('Invalid confirmation')
        row.consumed_at=datetime.utcnow();db.session.commit()
        # Confirmation grants no login, identity binding or business authorization.
        session['enrollment_notice_until']=time.time()+300
    except (BadSignature,ValueError,KeyError,TypeError):
        db.session.rollback()
        return jsonify(error='invalid_or_consumed_confirmation'),400
    response=redirect(ORIGIN+'/');response.headers['Cache-Control']='no-store';response.headers['Referrer-Policy']='no-referrer'
    return response

@bp.get('/api/dev/enrollment-notice')
def enrollment_notice():
    response=jsonify(pending_confirmation=time.time()<session.get('enrollment_notice_until',0))
    response.headers['Cache-Control']='no-store'
    return response

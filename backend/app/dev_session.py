"""DEV server deadlines and per-cookie serialization, including refresh rotation."""
import fcntl
import hashlib
import os
import re
from itsdangerous import BadSignature
from flask import request, g

def session_expired(values, now, idle, absolute):
    created=values.get("oidc_created_at",0)
    active=values.get("oidc_last_activity",0)
    return not created or not active or now < created or now < active or now >= created+absolute or now >= active+idle

def configure_sessions(app, directory):
    original=app.session_interface
    class SerializedSessionInterface(type(original)):
        def open_session(self, app, req):
            cookie=req.cookies.get(app.config['SESSION_COOKIE_NAME'])
            sid=None
            if cookie and len(cookie)<=256:
                try:sid=self._unsign(app,cookie) if self.use_signer else cookie
                except BadSignature:pass
            if sid and re.fullmatch(r"[A-Za-z0-9_-]{32,128}",sid) and g.get("dev_session_lock") is None:
                path=os.path.join(directory, "lock-"+hashlib.sha256(sid.encode()).hexdigest())
                handle=os.open(path,os.O_CREAT|os.O_RDWR,0o600)
                fcntl.flock(handle,fcntl.LOCK_EX)
                g.dev_session_lock=handle
            return super().open_session(app,req)
        def save_session(self, app, session, response):
            try:return super().save_session(app,session,response)
            finally:release()
    original.__class__=SerializedSessionInterface
    def release():
        handle=g.pop('dev_session_lock',None)
        if handle is not None:
            fcntl.flock(handle,fcntl.LOCK_UN);os.close(handle)
    app.teardown_request(lambda error:release())

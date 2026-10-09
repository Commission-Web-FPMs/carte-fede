"""Structured diagnostics without exception messages, SQL, request data or locals."""
import json
import logging
import os
import re
import sys
import traceback
from gunicorn.glogging import Logger

EVENTS = {"login_failed", "register_failed", "password_reset_email_failed",
          "auto_create_tables_failed", "unhandled_request_error"}


def diagnostics(exc_info):
    kind, error, tb = exc_info or (None, None, None)
    category = "none"
    if kind:
        module = kind.__module__
        category = kind.__name__ if module == "builtins" or module.startswith(("sqlalchemy", "psycopg", "smtplib")) else "ApplicationError"
    original = getattr(error, "orig", error)
    state = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    state = state if isinstance(state, str) and re.fullmatch(r"[0-9A-Z]{5}", state) else None
    # No directories, source lines, local variables, exception text or arguments.
    frames = [f"{os.path.basename(f.filename)}:{f.lineno}:{f.name}"
              for f in traceback.extract_tb(tb)] if tb else []
    return {"category": category, "sqlstate": state, "frames": frames[-8:]}


class PrivacyFormatter(logging.Formatter):
    def format(self, record):
        result = {"level": record.levelname, "logger": record.name}
        if record.name == "gunicorn.access":
            atoms = record.args if isinstance(record.args, dict) else {}
            method = atoms.get("m", "")
            result.update(event="http_access", method=method if method in
                          {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"} else "OTHER")
            status = str(atoms.get("s", ""))
            result["status"] = status if re.fullmatch(r"[1-5][0-9]{2}", status) else "unknown"
            duration = str(atoms.get("L", ""))
            result["duration"] = duration if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", duration) else "unknown"
        else:
            event = getattr(record, "safe_event", "runtime_log")
            result["event"] = event if event in EVENTS else "runtime_log"
            result.update(diagnostics(record.exc_info))
        # Deliberately never call getMessage()/formatException(): both may contain secrets.
        return json.dumps(result, ensure_ascii=True)


def configure_logging(app):
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(logging.StreamHandler())
    for logger in [root, app.logger, logging.getLogger("gunicorn.error"), logging.getLogger("gunicorn.access")]:
        for handler in logger.handlers:
            handler.setFormatter(PrivacyFormatter())
    for name in ["sqlalchemy.engine", "psycopg", "psycopg.pool"]:
        logging.getLogger(name).setLevel(logging.WARNING)


def log_exception(event, exc_info=None):
    from flask import current_app
    if event not in EVENTS:
        raise ValueError("Unknown diagnostic event")
    current_app.logger.error(event, extra={"safe_event": event},
                             exc_info=exc_info or sys.exc_info())


class SafeGunicornLogger(Logger):
    def setup(self, cfg):
        super().setup(cfg)
        for logger in [self.error_log, self.access_log]:
            for handler in logger.handlers:
                handler.setFormatter(PrivacyFormatter())

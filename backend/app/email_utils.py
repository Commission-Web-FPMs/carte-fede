import os
import smtplib
from email.message import EmailMessage

from flask import current_app


def _bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def send_email(to_address: str, subject: str, body_text: str):
    if os.getenv("APP_ENV") == "development":
        return  # Deliberately discard; no content, recipient or token logging.
    cfg = current_app.config
    mail_address = (cfg.get("MAIL_ADDRESS") or "").strip()
    mail_password = (cfg.get("MAIL_PASSWORD") or "").strip()
    if not mail_address or not mail_password:
        raise RuntimeError("MAIL_ADDRESS/MAIL_PASSWORD not configured")

    msg = EmailMessage()
    msg["Subject"] = subject
    from_name = (cfg.get("MAIL_FROM_NAME") or "").strip()
    msg["From"] = f"{from_name} <{mail_address}>" if from_name else mail_address
    msg["To"] = to_address
    msg.set_content(body_text)

    smtp_host = cfg.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(cfg.get("SMTP_PORT", 587))
    use_tls = _bool(cfg.get("SMTP_USE_TLS", True), True)
    use_ssl = _bool(cfg.get("SMTP_USE_SSL", False), False)

    if use_ssl:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10) as server:
            server.login(mail_address, mail_password)
            server.send_message(msg)
        return

    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
        server.ehlo()
        if use_tls:
            server.starttls()
            server.ehlo()
        server.login(mail_address, mail_password)
        server.send_message(msg)

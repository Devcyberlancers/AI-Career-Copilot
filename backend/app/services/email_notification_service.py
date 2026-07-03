import asyncio
import datetime
import hashlib
import logging
import os
import secrets
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from app.models.email_log import EmailLog

logger = logging.getLogger("app.services.email_notification")
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "disabled").strip().lower()
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", os.getenv("SMTP_USER", "")).strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", os.getenv("FROM_EMAIL", SMTP_USERNAME or "noreply@aicareercopilot.local")).strip()
SMTP_TLS = os.getenv("SMTP_TLS", "true").strip().lower() in {"1", "true", "yes", "on"}
BASE_FRONTEND_URL = os.getenv("BASE_FRONTEND_URL", os.getenv("FRONTEND_URL", "http://localhost:3000")).rstrip("/")
BACKEND_ROOT = Path(__file__).resolve().parents[2]
_email_outbox_value = os.getenv("EMAIL_OUTBOX_DIR", str(BACKEND_ROOT / "email_outbox"))
EMAIL_OUTBOX_DIR = Path(_email_outbox_value)
if not EMAIL_OUTBOX_DIR.is_absolute():
    EMAIL_OUTBOX_DIR = BACKEND_ROOT / EMAIL_OUTBOX_DIR
EMAIL_RETRY_ATTEMPTS = int(os.getenv("EMAIL_RETRY_ATTEMPTS", "3"))
EMAIL_RETRY_DELAY_SECONDS = float(os.getenv("EMAIL_RETRY_DELAY_SECONDS", "1"))
EMAIL_TOKEN_EXPIRY_MINUTES = int(os.getenv("EMAIL_TOKEN_EXPIRY", "60"))
PASSWORD_RESET_TOKEN_EXPIRY_MINUTES = int(os.getenv("PASSWORD_RESET_TOKEN_EXPIRY_MINUTES", "15"))
HIGH_MATCH_ALERT_THRESHOLD = int(os.getenv("HIGH_MATCH_ALERT_THRESHOLD", "90"))

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates" / "email"
env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


@dataclass(frozen=True)
class EmailTemplate:
    template_name: str
    subject: str


TEMPLATES = {
    "welcome": EmailTemplate("welcome.html", "Welcome to AI Career Copilot"),
    "verify_email": EmailTemplate("verify_email.html", "Verify your AI Career Copilot email"),
    "forgot_password": EmailTemplate("forgot_password.html", "Reset your AI Career Copilot password"),
    "password_changed": EmailTemplate("password_changed.html", "Your AI Career Copilot password changed"),
    "resume_ready": EmailTemplate("resume_ready.html", "Your tailored resume is ready"),
    "new_job_matches": EmailTemplate("new_job_matches.html", "Your new job matches are ready"),
    "high_match_alert": EmailTemplate("high_match_alert.html", "High match job alert"),
    "application_submitted": EmailTemplate("application_submitted.html", "Application submitted"),
    "application_failed": EmailTemplate("application_failed.html", "Application needs attention"),
    "interview_reminder": EmailTemplate("interview_reminder.html", "Interview reminder"),
    "weekly_report": EmailTemplate("weekly_report.html", "Your weekly career report"),
    "security_alert": EmailTemplate("security_alert.html", "Security alert for your account"),
    "usage_alert": EmailTemplate("usage_alert.html", "Usage limit alert"),
    "support_acknowledgement": EmailTemplate("support_acknowledgement.html", "We received your support request"),
    "account_deleted": EmailTemplate("account_deleted.html", "Your account has been deleted"),
}


def generate_secure_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_expiry(minutes: Optional[int] = None) -> datetime.datetime:
    return datetime.datetime.utcnow() + datetime.timedelta(minutes=minutes or EMAIL_TOKEN_EXPIRY_MINUTES)


def _plain_text_from_context(template_key: str, context: Dict[str, Any]) -> str:
    lines = [context.get("heading") or TEMPLATES.get(template_key, EmailTemplate("", "AI Career Copilot")).subject]
    for key in ("message", "body", "summary", "reason", "recommendations"):
        value = context.get(key)
        if value:
            lines.append(str(value))
    for key in ("dashboard_url", "verify_url", "reset_url", "download_url", "action_url"):
        value = context.get(key)
        if value:
            lines.append(f"{key.replace('_', ' ').title()}: {value}")
    return "\n\n".join(lines)


def render_template(template_key: str, context: Optional[Dict[str, Any]] = None) -> tuple[str, str, str]:
    context = dict(context or {})
    template_meta = TEMPLATES.get(template_key)
    if not template_meta:
        raise ValueError(f"Unknown email template: {template_key}")
    context.setdefault("app_name", "AI Career Copilot")
    context.setdefault("dashboard_url", f"{BASE_FRONTEND_URL}/dashboard")
    context.setdefault("base_frontend_url", BASE_FRONTEND_URL)
    html = env.get_template(template_meta.template_name).render(**context)
    text = _plain_text_from_context(template_key, context)
    return template_meta.subject, html, text


def _smtp_send(to_email: str, subject: str, html_body: str, text_body: str) -> None:
    if not SMTP_HOST or not SMTP_USERNAME or not SMTP_PASSWORD:
        raise RuntimeError("SMTP_HOST, SMTP_USERNAME/SMTP_USER, and SMTP_PASSWORD are required for SMTP email.")

    message = EmailMessage()
    message["From"] = SMTP_FROM
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(text_body or "")
    message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
        if SMTP_TLS:
            server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(message)


def _safe_file_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.lower())
    return cleaned[:80] or "email"


def _file_send(to_email: str, subject: str, html_body: str, text_body: str) -> None:
    EMAIL_OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    base_name = f"{timestamp}_{_safe_file_name(to_email)}_{_safe_file_name(subject)}"
    (EMAIL_OUTBOX_DIR / f"{base_name}.html").write_text(html_body, encoding="utf-8")
    (EMAIL_OUTBOX_DIR / f"{base_name}.txt").write_text(text_body or subject, encoding="utf-8")
    logger.info("Email written to local outbox: %s", EMAIL_OUTBOX_DIR / f"{base_name}.html")


def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str = "",
    db: Optional[Session] = None,
    user_id: Optional[int] = None,
    template_name: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    log: Optional[EmailLog] = None
    if db is not None:
        log = EmailLog(
            user_id=user_id,
            to_email=to_email,
            subject=subject,
            template_name=template_name,
            provider=EMAIL_PROVIDER,
            status="queued",
            metadata_json=metadata or {},
        )
        db.add(log)
        db.commit()
        db.refresh(log)

    if EMAIL_PROVIDER in {"", "disabled", "none", "log"}:
        logger.info("Email disabled. Would send '%s' to %s", subject, to_email)
        if log:
            log.status = "skipped"
            log.attempts = 0
            log.updated_at = datetime.datetime.utcnow()
            db.commit()
        return False

    last_error: Optional[Exception] = None
    for attempt in range(1, EMAIL_RETRY_ATTEMPTS + 1):
        try:
            if EMAIL_PROVIDER == "smtp":
                _smtp_send(to_email, subject, html_body, text_body)
            elif EMAIL_PROVIDER == "file":
                _file_send(to_email, subject, html_body, text_body)
            else:
                raise RuntimeError(f"Unsupported EMAIL_PROVIDER '{EMAIL_PROVIDER}'. Use smtp, file, or disabled.")
            if log:
                log.status = "sent"
                log.attempts = attempt
                log.sent_at = datetime.datetime.utcnow()
                log.updated_at = datetime.datetime.utcnow()
                db.commit()
            logger.info("Email sent to %s subject='%s' attempts=%s", to_email, subject, attempt)
            return True
        except Exception as exc:  # noqa: BLE001 - logged and retried intentionally
            last_error = exc
            logger.warning("Email send failed attempt=%s to=%s subject='%s': %s", attempt, to_email, subject, exc)
            if attempt < EMAIL_RETRY_ATTEMPTS:
                import time
                time.sleep(EMAIL_RETRY_DELAY_SECONDS * attempt)

    if log:
        log.status = "failed"
        log.attempts = EMAIL_RETRY_ATTEMPTS
        log.error_message = str(last_error) if last_error else "Unknown email failure"
        log.updated_at = datetime.datetime.utcnow()
        db.commit()
    return False


async def send_email_async(*args: Any, **kwargs: Any) -> bool:
    return await asyncio.to_thread(send_email, *args, **kwargs)


def send_template(
    to_email: str,
    template_key: str,
    context: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None,
    user_id: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    subject, html, text = render_template(template_key, context)
    return send_email(
        to_email=to_email,
        subject=subject,
        html_body=html,
        text_body=text,
        db=db,
        user_id=user_id,
        template_name=template_key,
        metadata=metadata,
    )


async def send_template_async(*args: Any, **kwargs: Any) -> bool:
    return await asyncio.to_thread(send_template, *args, **kwargs)


def send_bulk(recipients: Iterable[str], template_key: str, context: Optional[Dict[str, Any]] = None) -> dict:
    sent = 0
    failed = 0
    for recipient in recipients:
        if send_template(recipient, template_key, context):
            sent += 1
        else:
            failed += 1
    return {"sent": sent, "failed": failed}


def queue_email(template_key: str, to_email: str, context: Optional[Dict[str, Any]] = None, **kwargs: Any) -> dict:
    # Queue-friendly boundary: callers can replace this with Celery/RQ later without changing route code.
    sent = send_template(to_email=to_email, template_key=template_key, context=context, **kwargs)
    return {"queued": EMAIL_PROVIDER not in {"disabled", "none", ""}, "sent": sent}


# Compatibility wrapper used by signup.
def send_welcome_email(to_email: str, name: str = "", db: Optional[Session] = None, user_id: Optional[int] = None) -> bool:
    return send_template(
        to_email=to_email,
        template_key="welcome",
        context={
            "name": name or "there",
            "dashboard_url": f"{BASE_FRONTEND_URL}/dashboard",
            "upload_resume_url": f"{BASE_FRONTEND_URL}/dashboard",
            "verify_url": f"{BASE_FRONTEND_URL}/verify-email",
        },
        db=db,
        user_id=user_id,
    )


def send_resume_ready_email(to_email: str, name: str, job_title: str, company: str, ats_score: Any, download_url: str, db: Optional[Session] = None, user_id: Optional[int] = None) -> bool:
    return send_template(
        to_email=to_email,
        template_key="resume_ready",
        context={
            "name": name or "there",
            "job_title": job_title,
            "company": company,
            "ats_score": ats_score,
            "download_url": download_url,
        },
        db=db,
        user_id=user_id,
    )

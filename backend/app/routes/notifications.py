import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_user
from app.database.connection import get_db
from app.models.notification import Notification
from app.models.email_log import EmailLog
from app.models.limits import PlatformLimit
from app.models.user import User
from app.schemas.notifications import (
    ApplicationSettingsResponse,
    ApplicationSettingsUpdate,
    EmailLogResponse,
    LimitsResponse,
    NotificationResponse,
    NotificationSettingsResponse,
    NotificationSettingsUpdate,
    PlatformLimitUpdate,
    TestEmailRequest,
)
from app.services.email_notification_service import EMAIL_OUTBOX_DIR, EMAIL_PROVIDER, SMTP_FROM, SMTP_HOST, SMTP_PORT, SMTP_TLS, send_template
from app.services.limits_service import ensure_platform_limits, get_usage_limits
from app.services.notification_service import (
    get_or_create_application_settings,
    get_or_create_preferences,
    mark_notification_read,
)

router = APIRouter()


@router.get("/notifications", response_model=list[NotificationResponse])
def list_notifications(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Notification).filter(Notification.user_id == current_user.id).order_by(Notification.created_at.desc()).limit(100).all()


@router.post("/notifications/{notification_id}/read", response_model=NotificationResponse)
def read_notification(notification_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    notification = db.query(Notification).filter(Notification.id == notification_id, Notification.user_id == current_user.id).first()
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    return mark_notification_read(db, notification)




@router.get("/email/config")
def email_config(current_user: User = Depends(get_current_user)):
    return {
        "provider": EMAIL_PROVIDER,
        "smtp_host_configured": bool(SMTP_HOST),
        "smtp_port": SMTP_PORT,
        "smtp_from": SMTP_FROM,
        "smtp_tls": SMTP_TLS,
        "outbox_dir": str(EMAIL_OUTBOX_DIR),
        "enabled": EMAIL_PROVIDER == "file" or (EMAIL_PROVIDER == "smtp" and bool(SMTP_HOST)),
    }


@router.get("/email/history", response_model=list[EmailLogResponse])
def email_history(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(EmailLog).filter(EmailLog.user_id == current_user.id).order_by(EmailLog.created_at.desc()).limit(100).all()


@router.post("/email/test")
def send_test_email(request: TestEmailRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if request.template_name not in {"welcome", "new_job_matches", "weekly_report", "usage_alert"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported test template.")
    to_email = str(request.to_email or current_user.email)
    sent = send_template(
        to_email=to_email,
        template_key=request.template_name,
        context={
            "name": current_user.name,
            "jobs": [],
            "applications": 0,
            "ats_score": "Not available yet",
            "new_jobs": 0,
            "top_missing_skills": "Not available yet",
            "recommendations": "Open your dashboard to review current career activity.",
            "limit_name": "job discovery",
            "used": 0,
            "limit": 20,
            "reset_at": datetime.datetime.utcnow().isoformat(),
        },
        db=db,
        user_id=current_user.id,
    )
    return {"success": True, "sent": sent, "to_email": to_email}


@router.get("/settings/notifications", response_model=NotificationSettingsResponse)
def get_notification_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return get_or_create_preferences(db, current_user.id)


@router.post("/settings/notifications", response_model=NotificationSettingsResponse)
def update_notification_settings(payload: NotificationSettingsUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    preferences = get_or_create_preferences(db, current_user.id)
    for key, value in payload.model_dump().items():
        setattr(preferences, key, value)
    db.commit()
    db.refresh(preferences)
    return preferences


@router.get("/settings/application-mode", response_model=ApplicationSettingsResponse)
def get_application_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return get_or_create_application_settings(db, current_user.id)


@router.post("/settings/application-mode", response_model=ApplicationSettingsResponse)
def update_application_settings(payload: ApplicationSettingsUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    settings = get_or_create_application_settings(db, current_user.id)
    for key, value in payload.model_dump().items():
        setattr(settings, key, value)
    db.commit()
    db.refresh(settings)
    return settings


@router.get("/limits", response_model=list[LimitsResponse])
def usage_limits(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return get_usage_limits(db, current_user.id)


@router.get("/platform-limits")
def platform_limits(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ensure_platform_limits(db)
    rows = db.query(PlatformLimit).order_by(PlatformLimit.platform.asc()).all()
    return [{"platform": row.platform, "daily_search_limit": row.daily_search_limit, "daily_application_limit": row.daily_application_limit, "is_enabled": bool(row.is_enabled)} for row in rows]


@router.put("/platform-limits/{platform}")
def update_platform_limit(platform: str, payload: PlatformLimitUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    ensure_platform_limits(db, [platform])
    row = db.query(PlatformLimit).filter(PlatformLimit.platform == platform).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform limit not found.")
    row.daily_search_limit = payload.daily_search_limit
    row.daily_application_limit = payload.daily_application_limit
    row.is_enabled = 1 if payload.is_enabled else 0
    db.commit()
    db.refresh(row)
    return {
        "platform": row.platform,
        "daily_search_limit": row.daily_search_limit,
        "daily_application_limit": row.daily_application_limit,
        "is_enabled": bool(row.is_enabled),
    }

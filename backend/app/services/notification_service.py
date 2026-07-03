import datetime
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from app.models.notification import Notification
from app.models.user_preferences import UserPreferences
from app.models.application_settings import ApplicationSettings


def get_or_create_preferences(db: Session, user_id: int) -> UserPreferences:
    preferences = db.query(UserPreferences).filter(UserPreferences.user_id == user_id).first()
    if preferences:
        return preferences
    preferences = UserPreferences(user_id=user_id)
    db.add(preferences)
    db.commit()
    db.refresh(preferences)
    return preferences


def get_or_create_application_settings(db: Session, user_id: int) -> ApplicationSettings:
    settings = db.query(ApplicationSettings).filter(ApplicationSettings.user_id == user_id).first()
    if settings:
        return settings
    settings = ApplicationSettings(user_id=user_id)
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def create_notification(
    db: Session,
    user_id: int,
    type: str,
    title: str,
    message: str,
    action_url: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        action_url=action_url,
        metadata_json=metadata or {},
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


def mark_notification_read(db: Session, notification: Notification) -> Notification:
    notification.is_read = True
    notification.read_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(notification)
    return notification

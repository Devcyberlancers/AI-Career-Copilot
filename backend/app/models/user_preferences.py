import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship
from app.database.connection import Base


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    email_notifications = Column(Boolean, nullable=False, default=True)
    resume_ready = Column(Boolean, nullable=False, default=True)
    job_alerts = Column(Boolean, nullable=False, default=True)
    weekly_report = Column(Boolean, nullable=False, default=True)
    interview_reminder = Column(Boolean, nullable=False, default=True)
    security_alerts = Column(Boolean, nullable=False, default=True)
    marketing_emails = Column(Boolean, nullable=False, default=False)
    application_updates = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="preferences")

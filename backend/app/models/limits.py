import datetime
from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database.connection import Base


class DailyLimit(Base):
    __tablename__ = "daily_limits"
    __table_args__ = (UniqueConstraint("user_id", "limit_type", "platform", "date", name="uq_daily_limit_usage"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    limit_type = Column(String, nullable=False, default="job_search")
    platform = Column(String, nullable=False, default="global")
    date = Column(Date, nullable=False, default=datetime.date.today)
    used_count = Column(Integer, nullable=False, default=0)
    limit_count = Column(Integer, nullable=False, default=20)
    reset_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="daily_limits")


class PlatformLimit(Base):
    __tablename__ = "platform_limits"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String, unique=True, nullable=False, index=True)
    daily_search_limit = Column(Integer, nullable=False, default=20)
    daily_application_limit = Column(Integer, nullable=False, default=5)
    is_enabled = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship
from app.database.connection import Base


class ApplicationSettings(Base):
    __tablename__ = "application_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    mode = Column(String, nullable=False, default="manual")
    auto_apply_enabled = Column(Boolean, nullable=False, default=False)
    minimum_match_score = Column(Float, nullable=False, default=85)
    preferred_companies = Column(JSON, nullable=False, default=list)
    preferred_locations = Column(JSON, nullable=False, default=list)
    salary_range = Column(JSON, nullable=False, default=dict)
    experience_range = Column(JSON, nullable=False, default=dict)
    remote_only = Column(Boolean, nullable=False, default=False)
    exclude_companies = Column(JSON, nullable=False, default=list)
    maximum_daily_applications = Column(Integer, nullable=False, default=5)
    working_hours = Column(JSON, nullable=False, default=dict)
    daily_job_search_enabled = Column(Boolean, nullable=False, default=False)
    daily_job_search_time = Column(String, nullable=False, default="09:00")
    daily_job_search_platforms = Column(JSON, nullable=False, default=list)
    jobs_per_platform = Column(Integer, nullable=False, default=20)
    last_daily_job_search_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="application_settings")

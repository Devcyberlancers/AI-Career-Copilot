import datetime
from sqlalchemy import Column, DateTime, Integer, JSON, String, Text
from app.database.connection import Base


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    job_type = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="scheduled")
    payload_json = Column(JSON, nullable=False, default=dict)
    error_message = Column(Text, nullable=True)
    run_at = Column(DateTime, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

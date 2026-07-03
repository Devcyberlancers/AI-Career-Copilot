import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer
from app.database.connection import Base


class JobSearchLog(Base):
    __tablename__ = "job_search_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    jobs_discovered = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)

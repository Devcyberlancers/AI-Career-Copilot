import datetime
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from app.database.connection import Base


class AutoApplyLog(Base):
    __tablename__ = "auto_apply_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String, nullable=False, default="queued")
    match_score = Column(Float, nullable=True)
    reason = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    attempted_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="auto_apply_logs")

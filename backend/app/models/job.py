import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, JSON
from app.database.connection import Base

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    location = Column(String, nullable=True)
    description = Column(String, nullable=True)
    apply_url = Column(String, nullable=True)
    source = Column(String, nullable=True)
    status = Column(String, default="Discovered", nullable=False)
    match_score = Column(Float, nullable=True)
    semantic_score = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    matched_skills = Column(JSON, nullable=False, default=list)
    missing_skills = Column(JSON, nullable=False, default=list)
    matched_tools = Column(JSON, nullable=False, default=list)
    missing_tools = Column(JSON, nullable=False, default=list)
    experience_gap = Column(Float, nullable=False, default=0)
    score_breakdown_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

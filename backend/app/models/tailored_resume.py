import datetime
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from app.database.connection import Base


class TailoredResume(Base):
    __tablename__ = "tailored_resumes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True, index=True)
    job_title = Column(String, nullable=True)
    company = Column(String, nullable=True)
    job_description = Column(Text, nullable=True)
    tailored_resume_text = Column(Text, nullable=True)
    pdf_path = Column(String, nullable=True)
    pdf_url = Column(String, nullable=True)
    original_resume_path = Column(String, nullable=True)
    tailored_resume_path = Column(String, nullable=True)
    original_match_score = Column(Float, nullable=True)
    tailored_match_score = Column(Float, nullable=True)
    improvement_score = Column(Float, nullable=True)
    before_score = Column(Float, nullable=True)
    after_score = Column(Float, nullable=True)
    improvement = Column(Float, nullable=True)
    matched_keywords = Column(JSON, nullable=False, default=list)
    missing_keywords = Column(JSON, nullable=False, default=list)
    sections_modified = Column(JSON, nullable=False, default=list)
    resume_used = Column(String, nullable=True)
    recommendation = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    missing_skills = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

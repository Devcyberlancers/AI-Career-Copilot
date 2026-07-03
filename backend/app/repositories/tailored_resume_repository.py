from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.tailored_resume import TailoredResume


class TailoredResumeRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        user_id: int,
        job_id: Optional[int],
        job_title: str,
        company: str,
        job_description: str,
        tailored_resume_text: str,
        pdf_path: str,
        pdf_url: str,
        original_resume_path: Optional[str] = None,
        before_score: Optional[float] = None,
        after_score: Optional[float] = None,
        improvement: Optional[float] = None,
        matched_keywords: Optional[list[str]] = None,
        missing_keywords: Optional[list[str]] = None,
        sections_modified: Optional[list[str]] = None,
        resume_used: str = "tailored",
        recommendation: Optional[str] = None,
        reason: Optional[str] = None,
        confidence: Optional[float] = None,
        missing_skills: Optional[list[str]] = None,
    ) -> TailoredResume:
        record = TailoredResume(
            user_id=user_id,
            job_id=job_id,
            job_title=job_title,
            company=company,
            job_description=job_description,
            tailored_resume_text=tailored_resume_text,
            pdf_path=pdf_path,
            pdf_url=pdf_url,
            original_resume_path=original_resume_path,
            tailored_resume_path=pdf_path,
            before_score=before_score,
            after_score=after_score,
            improvement=improvement,
            original_match_score=before_score,
            tailored_match_score=after_score,
            improvement_score=improvement,
            matched_keywords=matched_keywords or [],
            missing_keywords=missing_keywords or [],
            sections_modified=sections_modified or [],
            resume_used=resume_used,
            recommendation=recommendation,
            reason=reason,
            confidence=confidence,
            missing_skills=missing_skills or [],
            updated_at=datetime.utcnow(),
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get(self, tailored_resume_id: int) -> Optional[TailoredResume]:
        return self.db.query(TailoredResume).filter(TailoredResume.id == tailored_resume_id).first()

    def list_for_user(self, user_id: int) -> list[TailoredResume]:
        return (
            self.db.query(TailoredResume)
            .filter(TailoredResume.user_id == user_id)
            .order_by(TailoredResume.created_at.desc())
            .all()
        )

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.candidate_profile import CandidateProfile
from app.models.resume import Resume
from app.services.match_score_service import rescore_jobs_for_user
from app.utils.resume_parser import (
    count_parsed_fields,
    is_debug_profile,
    parse_resume_text,
)
from app.utils.resume_text import extract_resume_text

logger = logging.getLogger("app.services.candidate_profile")


def upsert_parsed_candidate_profile(
    db: Session,
    user_id: int,
    parsed_profile: Dict[str, Any],
) -> CandidateProfile:
    profile = db.query(CandidateProfile).filter(
        CandidateProfile.user_id == user_id
    ).first()
    if profile:
        profile.parsed_profile_json = parsed_profile
        profile.updated_at = datetime.utcnow()
    else:
        profile = CandidateProfile(
            user_id=user_id,
            parsed_profile_json=parsed_profile,
        )
        db.add(profile)

    db.commit()
    db.refresh(profile)
    logger.info(
        "Saved candidate profile for user %s: parsed fields=%s, keys=%s",
        user_id,
        count_parsed_fields(parsed_profile),
        sorted(parsed_profile.keys()),
    )
    rescore_jobs_for_user(db, user_id, force=True)
    return profile


def get_or_rebuild_candidate_profile(
    db: Session,
    user_id: int,
) -> Optional[CandidateProfile]:
    profile = db.query(CandidateProfile).filter(
        CandidateProfile.user_id == user_id
    ).first()
    if profile and not is_debug_profile(profile.parsed_profile_json):
        return profile

    resume = db.query(Resume).filter(Resume.user_id == user_id).first()
    if not resume:
        return profile

    resume_text = extract_resume_text(resume.file_path)["resume_text"]
    logger.info(
        "Rebuilding candidate profile for user %s from stored resume; extracted text length=%s",
        user_id,
        len(resume_text),
    )
    if not resume_text.strip():
        return profile

    parsed_profile = parse_resume_text(resume_text)
    logger.info(
        "Rebuilt candidate profile for user %s: parsed fields=%s",
        user_id,
        count_parsed_fields(parsed_profile),
    )
    return upsert_parsed_candidate_profile(db, user_id, parsed_profile)

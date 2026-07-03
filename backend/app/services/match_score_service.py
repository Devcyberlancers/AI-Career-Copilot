import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.candidate_profile import CandidateProfile
from app.models.job import Job
from app.models.profile import UserProfile
from app.services.job_match_ai_service import job_match_ai_service

logger = logging.getLogger("app.services.match_score")


def _user_profile_dict(profile: UserProfile) -> Dict[str, Any]:
    return {
        "name": profile.full_name,
        "location": profile.location,
        "desired_role": profile.desired_role,
        "skills": profile.skills or [],
        "projects": profile.projects or [],
        "certifications": profile.certifications or [],
        "education": [{
            "degree": profile.degree,
            "college": profile.college,
            "graduation_year": profile.graduation_year,
        }],
        "experience": [{
            "designation": profile.current_designation,
            "company": profile.current_company,
        }],
        "years_of_experience": profile.years_experience,
    }


def _profile_dict(profile: Any) -> Dict[str, Any]:
    if isinstance(profile, CandidateProfile) or hasattr(profile, "parsed_profile_json"):
        parsed = profile.parsed_profile_json or {}
        nested = parsed.get("candidate_profile")
        return nested if isinstance(nested, dict) else parsed
    if isinstance(profile, UserProfile) or (
        hasattr(profile, "skills") and hasattr(profile, "years_experience")
    ):
        return _user_profile_dict(profile)
    if isinstance(profile, dict):
        nested = profile.get("candidate_profile")
        return nested if isinstance(nested, dict) else profile
    return {}


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _merge_profile_sources(
    parsed_profile: Optional[CandidateProfile],
    user_profile: Optional[UserProfile],
) -> Dict[str, Any]:
    merged = _user_profile_dict(user_profile) if user_profile else {}
    parsed = _profile_dict(parsed_profile) if parsed_profile else {}
    for key, value in parsed.items():
        if _has_value(value):
            merged[key] = value
    return merged


def calculate_job_match(candidate_profile: Any, job: Any) -> Dict[str, Any]:
    return job_match_ai_service.generate_match_score(_profile_dict(candidate_profile), job)


def load_candidate_profile_for_scoring(db: Session, user_id: int) -> Dict[str, Any]:
    parsed_profile = db.query(CandidateProfile).filter(
        CandidateProfile.user_id == user_id
    ).first()
    user_profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    return _merge_profile_sources(parsed_profile, user_profile)


def apply_match_result(job: Job, result: Dict[str, Any]) -> None:
    job.match_score = result["match_score"]
    job.semantic_score = result["semantic_score"]
    job.confidence = result.get("confidence")
    job.matched_skills = result["matched_skills"]
    job.missing_skills = result["missing_skills"]
    job.matched_tools = result.get("matched_tools", [])
    job.missing_tools = result.get("missing_tools", [])
    job.experience_gap = result.get("experience_gap", 0)
    job.score_breakdown_json = {
        **result.get("score_breakdown", {}),
        "recommendations": result.get("recommendations", []),
    }


def score_job_for_user(db: Session, job: Job) -> Optional[Dict[str, Any]]:
    try:
        result = job_match_ai_service.generate_match_score(
            load_candidate_profile_for_scoring(db, job.user_id),
            job,
        )
    except Exception as exc:
        logger.exception("Embedding match scoring failed for job %s: %s", job.id, exc)
        job.match_score = None
        job.semantic_score = None
        job.score_breakdown_json = {
            "scoring_engine": "huggingface_sentence_transformer",
            "error": str(exc),
        }
        return None

    apply_match_result(job, result)
    return result


def rescore_jobs_for_user(db: Session, user_id: int, force: bool = False) -> int:
    jobs = db.query(Job).filter(Job.user_id == user_id).all()
    rescored = 0
    for job in jobs:
        breakdown = job.score_breakdown_json or {}
        engine = breakdown.get("scoring_engine") if isinstance(breakdown, dict) else None
        if force or job.semantic_score is None or engine != "huggingface_sentence_transformer":
            if score_job_for_user(db, job):
                rescored += 1
    if jobs:
        db.commit()
    return rescored

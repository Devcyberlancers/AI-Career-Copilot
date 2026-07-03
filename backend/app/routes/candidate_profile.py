from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.candidate_profile import CandidateProfile
from app.models.user import User
from app.schemas.candidate_profile import (
    CandidateProfileResponse,
    CandidateProfileStore,
    CandidateProfileStoredResponse,
)
from app.auth.dependencies import get_current_user
from app.services.candidate_profile_service import (
    get_or_rebuild_candidate_profile,
    upsert_parsed_candidate_profile,
)
from app.utils.resume_parser import is_debug_profile

router = APIRouter()


def normalize_profile_json(profile_data: CandidateProfileStore) -> Dict[str, Any]:
    parsed_profile = profile_data.parsed_profile_json or profile_data.candidate_profile
    if not parsed_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="parsed_profile_json or candidate_profile is required.",
        )
    nested = parsed_profile.get("candidate_profile")
    if isinstance(nested, dict):
        parsed_profile = nested
    if is_debug_profile(parsed_profile):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Candidate profile payload contains no parsed resume fields.",
        )
    return parsed_profile


def profile_value(parsed_profile: Dict[str, Any], key: str, default: Any) -> Any:
    value = parsed_profile.get(key, default)
    return default if value is None else value


def profile_list(parsed_profile: Dict[str, Any], key: str) -> list[Any]:
    value = profile_value(parsed_profile, key, [])
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def candidate_profile_payload(profile: CandidateProfile) -> CandidateProfileResponse:
    parsed_profile = profile.parsed_profile_json or {}
    years_of_experience = profile_value(
        parsed_profile,
        "years_of_experience",
        profile_value(parsed_profile, "years_experience", 0),
    )

    return CandidateProfileResponse(
        user_id=profile.user_id,
        parsed_profile_json=parsed_profile,
        raw_resume_text=profile_value(parsed_profile, "raw_resume_text", ""),
        name=profile_value(parsed_profile, "name", ""),
        email=profile_value(parsed_profile, "email", ""),
        phone=profile_value(parsed_profile, "phone", ""),
        location=profile_value(parsed_profile, "location", ""),
        skills=profile_list(parsed_profile, "skills"),
        projects=profile_list(parsed_profile, "projects"),
        certifications=profile_list(parsed_profile, "certifications"),
        experience=profile_list(parsed_profile, "experience"),
        education=profile_list(parsed_profile, "education"),
        tools=profile_list(parsed_profile, "tools"),
        languages=profile_list(parsed_profile, "languages"),
        years_of_experience=years_of_experience,
        career_level=profile_value(parsed_profile, "career_level", ""),
        summary=profile_value(parsed_profile, "summary", ""),
        updated_at=profile.updated_at,
    )


def upsert_candidate_profile(
    profile_data: CandidateProfileStore,
    db: Session,
) -> tuple[CandidateProfile, str]:
    if profile_data.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id is required for this endpoint.",
        )

    user = db.query(User).filter(User.id == profile_data.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {profile_data.user_id} not found.",
        )

    parsed_profile = normalize_profile_json(profile_data)
    existing = db.query(CandidateProfile).filter(
        CandidateProfile.user_id == profile_data.user_id
    ).first()
    action = "updated" if existing else "created"
    profile = upsert_parsed_candidate_profile(
        db,
        profile_data.user_id,
        parsed_profile,
    )
    return profile, action


@router.post("", response_model=CandidateProfileResponse)
def create_or_update_candidate_profile(
    profile_data: CandidateProfileStore,
    db: Session = Depends(get_db),
):
    profile, _ = upsert_candidate_profile(profile_data, db)
    return candidate_profile_payload(profile)


@router.post("/store", response_model=CandidateProfileStoredResponse)
def store_candidate_profile(
    profile_data: CandidateProfileStore,
    db: Session = Depends(get_db),
):
    profile, action = upsert_candidate_profile(profile_data, db)

    return {
        "success": True,
        "status": action,
        "candidate_profile": candidate_profile_payload(profile),
    }


@router.post("/me", response_model=CandidateProfileResponse)
def create_or_update_my_candidate_profile(
    profile_data: CandidateProfileStore,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    print("Authenticated User:", current_user.id)
    profile_data.user_id = current_user.id
    profile, _ = upsert_candidate_profile(profile_data, db)
    return candidate_profile_payload(profile)


@router.get("/me", response_model=CandidateProfileResponse)
def get_my_candidate_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    print("Authenticated User:", current_user.id)
    profile = get_or_rebuild_candidate_profile(db, current_user.id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate profile not found.",
        )
    return candidate_profile_payload(profile)


@router.get("/{user_id}", response_model=CandidateProfileResponse)
def get_candidate_profile(
    user_id: int,
    db: Session = Depends(get_db),
):
    profile = get_or_rebuild_candidate_profile(db, user_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate profile not found.",
        )
    return candidate_profile_payload(profile)

import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.models.profile import UserProfile
from app.models.resume import Resume
from app.models.user import User
from app.schemas.profile import ProfileCreate, ProfileUpdate, ProfileResponse
from app.auth.dependencies import get_current_user
from app.utils.resume_intelligence import send_resume_intelligence_webhook
from app.utils.resume_text import extract_resume_text
from app.services.match_score_service import rescore_jobs_for_user

router = APIRouter()
logger = logging.getLogger("app.routes.profile")

@router.post("/create", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
def create_profile(
    profile_data: ProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Prevent duplicate profile creation
    existing_profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if existing_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile already exists for this user. Please update the existing profile instead."
        )
        
    # 2. Serialize nested Pydantic models to dict lists
    serialized_projects = [p.model_dump() for p in profile_data.projects]
    serialized_certs = [c.model_dump() for c in profile_data.certifications]
    
    # 3. Save UserProfile
    new_profile = UserProfile(
        user_id=current_user.id,
        full_name=profile_data.full_name,
        email=profile_data.email,
        phone=profile_data.phone,
        location=profile_data.location,
        desired_role=profile_data.desired_role,
        years_experience=profile_data.years_experience,
        current_designation=profile_data.current_designation,
        current_company=profile_data.current_company,
        degree=profile_data.degree,
        college=profile_data.college,
        graduation_year=profile_data.graduation_year,
        skills=profile_data.skills,
        projects=serialized_projects,
        certifications=serialized_certs,
        desired_job_title=profile_data.desired_job_title,
        preferred_location=profile_data.preferred_location,
        expected_salary=profile_data.expected_salary,
        work_mode=profile_data.work_mode,
        max_applications_per_day=profile_data.max_applications_per_day,
        job_search_status=profile_data.job_search_status
    )
    
    db.add(new_profile)
    db.commit()
    db.refresh(new_profile)
    rescore_jobs_for_user(db, current_user.id, force=True)

    resume = db.query(Resume).filter(Resume.user_id == current_user.id).first()
    if resume:
        resume_text = extract_resume_text(resume.file_path)["resume_text"]
        logger.info(f"Extracted resume text length: {len(resume_text)}")
        send_resume_intelligence_webhook(current_user, resume, resume_text, db, profile=new_profile, event="profile_created")
    
    return new_profile

@router.get("/me", response_model=ProfileResponse)
def get_my_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profile setup found. Please build your profile first."
        )
    return profile

@router.put("/update", response_model=ProfileResponse)
def update_profile(
    profile_data: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profile found to update."
        )
        
    # Serialize nested schemas
    serialized_projects = [p.model_dump() for p in profile_data.projects]
    serialized_certs = [c.model_dump() for c in profile_data.certifications]
    
    # Update fields
    profile.full_name = profile_data.full_name
    profile.email = profile_data.email
    profile.phone = profile_data.phone
    profile.location = profile_data.location
    profile.desired_role = profile_data.desired_role
    profile.years_experience = profile_data.years_experience
    profile.current_designation = profile_data.current_designation
    profile.current_company = profile_data.current_company
    profile.degree = profile_data.degree
    profile.college = profile_data.college
    profile.graduation_year = profile_data.graduation_year
    profile.skills = profile_data.skills
    profile.projects = serialized_projects
    profile.certifications = serialized_certs
    profile.desired_job_title = profile_data.desired_job_title
    profile.preferred_location = profile_data.preferred_location
    profile.expected_salary = profile_data.expected_salary
    profile.work_mode = profile_data.work_mode
    profile.max_applications_per_day = profile_data.max_applications_per_day
    profile.job_search_status = profile_data.job_search_status
    profile.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(profile)
    rescore_jobs_for_user(db, current_user.id, force=True)

    resume = db.query(Resume).filter(Resume.user_id == current_user.id).first()
    if resume:
        resume_text = extract_resume_text(resume.file_path)["resume_text"]
        logger.info(f"Extracted resume text length: {len(resume_text)}")
        send_resume_intelligence_webhook(current_user, resume, resume_text, db, profile=profile, event="profile_updated")
    
    return profile

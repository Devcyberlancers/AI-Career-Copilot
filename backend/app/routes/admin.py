from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database.connection import get_db
from app.models.user import User
from app.schemas.user import UserResponse
from app.auth.dependencies import get_current_user

router = APIRouter()

def require_admin(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have administrative privileges"
        )
    return current_user

from typing import Optional
from app.models.profile import UserProfile
from app.models.resume import Resume
from app.models.job import Job
from app.models.job_search_log import JobSearchLog
from app.utils.job_source import SUPPORTED_JOB_SOURCES, apply_supported_job_filter, is_supported_job_source

DAILY_DISCOVERY_LIMIT = 20

@router.get("/users")
def get_all_users(
    desired_role: Optional[str] = None,
    skills: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    query = db.query(User)
    
    # Filter by profile criteria if requested
    if desired_role or skills:
        query = query.join(UserProfile)
        if desired_role:
            query = query.filter(UserProfile.desired_role.ilike(f"%{desired_role}%"))
        if skills:
            query = query.filter(UserProfile.skills.like(f"%{skills}%"))
            
    users = query.order_by(User.id.asc()).all()
    
    results = []
    for u in users:
        profile = db.query(UserProfile).filter(UserProfile.user_id == u.id).first()
        resume = db.query(Resume).filter(Resume.user_id == u.id).first()
        
        results.append({
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "is_admin": u.is_admin,
            "created_at": u.created_at,
            "profile": {
                "id": profile.id,
                "full_name": profile.full_name,
                "email": profile.email,
                "phone": profile.phone,
                "location": profile.location,
                "desired_role": profile.desired_role,
                "years_experience": profile.years_experience,
                "current_designation": profile.current_designation,
                "current_company": profile.current_company,
                "degree": profile.degree,
                "college": profile.college,
                "graduation_year": profile.graduation_year,
                "skills": profile.skills,
                "projects": profile.projects,
                "certifications": profile.certifications,
                "desired_job_title": profile.desired_job_title,
                "preferred_location": profile.preferred_location,
                "expected_salary": profile.expected_salary,
                "work_mode": profile.work_mode,
                "max_applications_per_day": profile.max_applications_per_day,
                "job_search_status": profile.job_search_status,
            } if profile else None,
            "resume": {
                "id": resume.id,
                "file_name": resume.file_name,
                "file_type": resume.file_type,
                "file_size": resume.file_size,
                "uploaded_at": resume.uploaded_at,
            } if resume else None
        })
        
    return results

@router.get("/monitoring/summary")
def get_monitoring_summary(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    window_start = datetime.utcnow() - timedelta(hours=24)
    users = db.query(User).all()
    students = [u for u in users if not u.is_admin]
    profiles = db.query(UserProfile).all()
    resumes = db.query(Resume).all()
    jobs = apply_supported_job_filter(db.query(Job)).all()
    logs = db.query(JobSearchLog).filter(JobSearchLog.created_at > window_start).all()

    discoveries_by_user = {}
    for log in logs:
        discoveries_by_user[log.user_id] = discoveries_by_user.get(log.user_id, 0) + log.jobs_discovered

    students_at_limit = [
        user_id for user_id, count in discoveries_by_user.items()
        if count >= DAILY_DISCOVERY_LIMIT
    ]

    return {
        "total_users": len(users),
        "total_students": len(students),
        "admin_users": len(users) - len(students),
        "profiles_completed": len(profiles),
        "resumes_uploaded": len(resumes),
        "total_jobs": len(jobs),
        "jobs_discovered_last_24h": sum(log.jobs_discovered for log in logs),
        "students_at_daily_limit": len(students_at_limit),
        "daily_limit": DAILY_DISCOVERY_LIMIT,
    }

@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    if admin.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own administrator account"
        )
        
    user_to_delete = db.query(User).filter(User.id == user_id).first()
    if not user_to_delete:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
        
    db.delete(user_to_delete)
    db.commit()
    return {"message": "User deleted successfully"}

@router.post("/users/{user_id}/toggle-admin", response_model=UserResponse)
def toggle_admin(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    if admin.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot change your own administrator status"
        )
        
    user_to_toggle = db.query(User).filter(User.id == user_id).first()
    if not user_to_toggle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
        
    user_to_toggle.is_admin = not user_to_toggle.is_admin
    db.commit()
    db.refresh(user_to_toggle)
    return user_to_toggle

@router.get("/users/{user_id}/details")
def get_user_details(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    profile = db.query(UserProfile).filter(UserProfile.user_id == u.id).first()
    resume = db.query(Resume).filter(Resume.user_id == u.id).first()
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "is_admin": u.is_admin,
        "created_at": u.created_at,
        "profile": {
            "id": profile.id,
            "full_name": profile.full_name,
            "email": profile.email,
            "phone": profile.phone,
            "location": profile.location,
            "desired_role": profile.desired_role,
            "years_experience": profile.years_experience,
            "current_designation": profile.current_designation,
            "current_company": profile.current_company,
            "degree": profile.degree,
            "college": profile.college,
            "graduation_year": profile.graduation_year,
            "skills": profile.skills,
            "projects": profile.projects,
            "certifications": profile.certifications,
            "desired_job_title": profile.desired_job_title,
            "preferred_location": profile.preferred_location,
            "expected_salary": profile.expected_salary,
            "work_mode": profile.work_mode,
            "max_applications_per_day": profile.max_applications_per_day,
            "job_search_status": profile.job_search_status,
        } if profile else None,
        "resume": {
            "id": resume.id,
            "file_name": resume.file_name,
            "file_type": resume.file_type,
            "file_size": resume.file_size,
            "uploaded_at": resume.uploaded_at,
        } if resume else None
    }

@router.get("/jobs")
def get_all_jobs(
    source: Optional[str] = None,
    status: Optional[str] = None,
    company: Optional[str] = None,
    title: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    query = apply_supported_job_filter(db.query(Job))
    
    if source and not is_supported_job_source(source):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {', '.join(SUPPORTED_JOB_SOURCES)} sources are supported at this time."
        )
    if source:
        query = query.filter(Job.source == source)
    if status:
        query = query.filter(Job.status == status)
    if company:
        query = query.filter(Job.company.ilike(f"%{company}%"))
    if title:
        query = query.filter(Job.title.ilike(f"%{title}%"))
        
    jobs = query.order_by(Job.created_at.desc()).all()
    
    results = []
    for j in jobs:
        user_info = db.query(User).filter(User.id == j.user_id).first()
        results.append({
            "id": j.id,
            "user_id": j.user_id,
            "user_name": user_info.name if user_info else "Unknown",
            "user_email": user_info.email if user_info else "Unknown",
            "title": j.title,
            "company": j.company,
            "location": j.location,
            "description": j.description,
            "apply_url": j.apply_url,
            "source": j.source,
            "status": j.status,
            "match_score": j.match_score,
            "semantic_score": j.semantic_score,
            "matched_skills": j.matched_skills or [],
            "missing_skills": j.missing_skills or [],
            "matched_tools": j.matched_tools or [],
            "missing_tools": j.missing_tools or [],
            "experience_gap": j.experience_gap or 0,
            "score_breakdown_json": j.score_breakdown_json or {},
            "created_at": j.created_at,
            "updated_at": j.updated_at
        })
    return results

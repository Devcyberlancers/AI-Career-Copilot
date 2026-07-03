from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.models.job import Job
from app.models.tailored_resume import TailoredResume
from app.database.connection import get_db
from app.utils.job_source import apply_supported_job_filter

router = APIRouter()

@router.get("/stats")
def get_dashboard_stats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_jobs = apply_supported_job_filter(db.query(Job).filter(Job.user_id == current_user.id))
    total_jobs = user_jobs.count()
    saved_jobs = user_jobs.filter(Job.status == "Saved").count()
    applied_jobs = user_jobs.filter(Job.status == "Applied").count()
    skipped_jobs = user_jobs.filter(Job.status == "Skipped").count()
    tailored_resumes = db.query(TailoredResume).filter(TailoredResume.user_id == current_user.id).count()

    return {
        "user": {
            "id": current_user.id,
            "name": current_user.name,
            "email": current_user.email,
            "is_admin": current_user.is_admin
        },
        "stats": {
            "total_applications": total_jobs,
            "jobs_found": total_jobs,
            "skipped_jobs": skipped_jobs,
            "saved_jobs": saved_jobs,
            "applied_jobs": applied_jobs,
            "tailored_resumes": tailored_resumes,
            "interviews": saved_jobs,  # Backward compatible alias for Saved Jobs
            "offers": applied_jobs      # Backward compatible alias for Applied Jobs
        }
    }

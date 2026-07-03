import math
import logging
import re
from datetime import datetime, timedelta
from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Dict, List, Optional, Tuple
from app.database.connection import get_db
from app.models.job import Job
from app.models.job_search_log import JobSearchLog
from app.models.user import User
from app.models.profile import UserProfile
from app.schemas.job import JobCreate, JobMatchAnalysisResponse, JobStatusUpdate, JobResponse
from app.auth.dependencies import get_current_user
from app.utils.job_search import search_jobs_for_user
from app.utils.job_ranking import rank_jobs_for_user
from app.services.match_score_service import rescore_jobs_for_user, score_job_for_user
from app.utils.job_source import (
    SUPPORTED_JOB_SOURCE,
    SUPPORTED_JOB_SOURCES,
    apply_supported_job_filter,
    is_supported_job_source,
    is_valid_job_url_for_source,
)

router = APIRouter()
logger = logging.getLogger("app.routes.jobs")
DAILY_DISCOVERY_LIMIT = 20
DISCOVERY_WINDOW_HOURS = 24

def normalize_job_text(value: Optional[str]) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", (value or "").lower())
    return " ".join(normalized.split())

def job_fingerprint(title: Optional[str], company: Optional[str], location: Optional[str]) -> Tuple[str, str, str]:
    return (
        normalize_job_text(title),
        normalize_job_text(company),
        normalize_job_text(location),
    )

def prune_duplicate_jobs_for_user(db: Session, user_id: int) -> int:
    status_priority = {
        "Applied": 5,
        "Saved": 4,
        "Discovered": 2,
        "Skipped": 1,
    }
    grouped_jobs: Dict[Tuple[str, str, str, str], List[Job]] = {}
    user_jobs = db.query(Job).filter(
        Job.user_id == user_id,
        Job.source.in_(SUPPORTED_JOB_SOURCES)
    ).all()

    for job in user_jobs:
        key = ((job.source or ""), *job_fingerprint(job.title, job.company, job.location))
        if not all(key):
            continue
        grouped_jobs.setdefault(key, []).append(job)

    removed_count = 0
    for duplicate_group in grouped_jobs.values():
        if len(duplicate_group) < 2:
            continue

        keep_job = sorted(
            duplicate_group,
            key=lambda job: (
                -status_priority.get(job.status, 0),
                job.created_at,
                job.id,
            )
        )[0]

        for duplicate_job in duplicate_group:
            if duplicate_job.id == keep_job.id:
                continue
            db.delete(duplicate_job)
            removed_count += 1

    if removed_count:
        db.commit()
        logger.info("Pruned %s duplicate job(s) for user %s", removed_count, user_id)

    return removed_count

def utc_isoformat(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat() + "Z"

def get_discovery_limit_state(db: Session, user_id: int, source: Optional[str] = None) -> dict:
    now = datetime.utcnow()
    window_start = now - timedelta(hours=DISCOVERY_WINDOW_HOURS)
    logs = db.query(JobSearchLog).filter(
        JobSearchLog.user_id == user_id,
        JobSearchLog.created_at > window_start,
        JobSearchLog.jobs_discovered > 0,
    ).order_by(JobSearchLog.created_at.asc()).all()

    # New per-platform limits are based on recently stored unique jobs. The legacy
    # job_search_logs table has no source column, so it is only used for old global checks.
    logged_discovered_count = 0 if source else sum(log.jobs_discovered for log in logs)

    recent_unique_jobs: Dict[Tuple[str, str, str, str], Job] = {}
    recent_query = db.query(Job).filter(
        Job.user_id == user_id,
        Job.source.in_(SUPPORTED_JOB_SOURCES),
        Job.created_at > window_start,
    )
    if source and source != "All":
        recent_query = recent_query.filter(Job.source == source)
    recent_jobs = recent_query.order_by(Job.created_at.asc()).all()
    for job in recent_jobs:
        key = ((job.source or ""), *job_fingerprint(job.title, job.company, job.location))
        if all(key) and key not in recent_unique_jobs:
            recent_unique_jobs[key] = job

    job_created_count = len(recent_unique_jobs)
    discovered_count = max(logged_discovered_count, job_created_count)
    remaining_jobs = max(0, DAILY_DISCOVERY_LIMIT - discovered_count)

    next_available_at = None
    remaining_seconds = 0
    if remaining_jobs <= 0:
        cumulative_expiring = 0
        if logged_discovered_count >= job_created_count and logs:
            for log in logs:
                cumulative_expiring += log.jobs_discovered
                if discovered_count - cumulative_expiring < DAILY_DISCOVERY_LIMIT:
                    next_available_at = log.created_at + timedelta(hours=DISCOVERY_WINDOW_HOURS)
                    break
        else:
            unique_jobs_by_time = sorted(recent_unique_jobs.values(), key=lambda job: job.created_at)
            if len(unique_jobs_by_time) >= DAILY_DISCOVERY_LIMIT:
                next_available_at = unique_jobs_by_time[0].created_at + timedelta(hours=DISCOVERY_WINDOW_HOURS)

        if next_available_at:
            remaining_seconds = max(0, math.ceil((next_available_at - now).total_seconds()))

    return {
        "jobs_discovered_in_last_24_hours": discovered_count,
        "jobs_discovered_from_logs": logged_discovered_count,
        "jobs_discovered_from_recent_jobs": job_created_count,
        "remaining_jobs": remaining_jobs,
        "next_available_at": utc_isoformat(next_available_at) if next_available_at else None,
        "remaining_seconds": remaining_seconds,
    }


def get_profile_search_terms(db: Session, current_user: User) -> Tuple[str, str, Optional[UserProfile]]:
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()

    query = ""
    location = ""
    if profile:
        query = (profile.desired_job_title or profile.desired_role or "").strip()
        location = (profile.preferred_location or profile.location or "").strip()

    if not query:
        query = (current_user.desired_role or "").strip()
    if not location:
        location = (current_user.location or "").strip()
    return query, location, profile


def max_results_for_profile(profile: Optional[UserProfile], limit_state: dict) -> int:
    max_results = 20
    if profile and profile.max_applications_per_day:
        max_results = max(1, min(profile.max_applications_per_day, 100))
    return min(max_results, limit_state["remaining_jobs"], DAILY_DISCOVERY_LIMIT)


def platform_stats_for_user(db: Session, user_id: int) -> dict:
    rows = db.query(
        Job.source,
        func.count(Job.id),
        func.max(Job.updated_at),
    ).filter(
        Job.user_id == user_id,
        Job.source.in_(SUPPORTED_JOB_SOURCES),
    ).group_by(Job.source).all()

    by_source = {
        source: {
            "source": source,
            "count": 0,
            "last_refresh_at": None,
        }
        for source in SUPPORTED_JOB_SOURCES
    }
    for source, count, last_refresh_at in rows:
        if source in by_source:
            by_source[source] = {
                "source": source,
                "count": count,
                "last_refresh_at": utc_isoformat(last_refresh_at) if last_refresh_at else None,
            }
    return {
        "total": sum(item["count"] for item in by_source.values()),
        "sources": list(by_source.values()),
    }


def execute_discovery_for_source(
    db: Session,
    current_user: User,
    source: str,
    max_results_override: Optional[int] = None,
) -> dict:
    source = source or SUPPORTED_JOB_SOURCE
    if source == "All":
        platform_results = []
        total_stored = 0
        total_skipped = 0
        for platform in SUPPORTED_JOB_SOURCES:
            try:
                result = execute_discovery_for_source(db, current_user, platform, max_results_override=max_results_override)
                platform_results.append(result)
                total_stored += int(result.get("jobs_stored") or result.get("jobs_discovered") or 0)
                total_skipped += int(result.get("jobs_skipped") or 0)
            except HTTPException as exc:
                platform_results.append({
                    "source": platform,
                    "success": False,
                    "error": exc.detail,
                    "status_code": exc.status_code,
                })
            except Exception as exc:
                logger.exception("Scheduled/discover-all failed for source %s user %s", platform, current_user.id)
                platform_results.append({"source": platform, "success": False, "error": str(exc)})
        return {
            "success": True,
            "source": "All",
            "platform_results": platform_results,
            "jobs_stored": total_stored,
            "jobs_skipped": total_skipped,
            "platform_stats": platform_stats_for_user(db, current_user.id),
        }

    if source != "All" and not is_supported_job_source(source):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only All, {', '.join(SUPPORTED_JOB_SOURCES)} sources are supported at this time."
        )

    query, location, profile = get_profile_search_terms(db, current_user)
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Add a desired job title in your profile before fetching {source} jobs."
        )

    limit_state = get_discovery_limit_state(db, current_user.id, source if source != "All" else None)
    if limit_state["remaining_jobs"] <= 0:
        return {
            "success": False,
            "error": "DAILY_LIMIT_REACHED",
            "next_available_at": limit_state["next_available_at"],
            "remaining_seconds": limit_state["remaining_seconds"],
            "jobs_discovered_in_last_24_hours": limit_state["jobs_discovered_in_last_24_hours"],
            "daily_limit": DAILY_DISCOVERY_LIMIT,
        }

    max_results = max_results_for_profile(profile, limit_state)
    if max_results_override is not None:
        max_results = min(max(1, max_results_override), limit_state["remaining_jobs"], DAILY_DISCOVERY_LIMIT)

    try:
        result = search_jobs_for_user(current_user.id, query, location, max_results=max_results, source=source)
    except Exception as exc:
        logger.error(f"Failed to discover jobs for user {current_user.id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc) or "Could not fetch jobs from the job search service."
        )

    jobs_discovered = int(result.get("jobs_stored") or 0)
    if jobs_discovered > 0:
        db.add(JobSearchLog(
            user_id=current_user.id,
            jobs_discovered=jobs_discovered
        ))
        db.commit()

    updated_limit_state = get_discovery_limit_state(db, current_user.id, source if source != "All" else None)
    pruned_count = prune_duplicate_jobs_for_user(db, current_user.id)

    stored_jobs = apply_supported_job_filter(
        db.query(Job).filter(Job.user_id == current_user.id)
    ).order_by(Job.created_at.desc()).all()

    return {
        **result,
        "source": source,
        "max_results": max_results,
        "stored_jobs_count": len(stored_jobs),
        "duplicates_removed": pruned_count,
        "jobs_discovered_in_last_24_hours": updated_limit_state["jobs_discovered_in_last_24_hours"],
        "remaining_jobs": updated_limit_state["remaining_jobs"],
        "daily_limit": DAILY_DISCOVERY_LIMIT,
        "next_available_at": updated_limit_state["next_available_at"],
        "remaining_seconds": updated_limit_state["remaining_seconds"],
        "platform_stats": platform_stats_for_user(db, current_user.id),
    }

@router.post("/store", status_code=status.HTTP_200_OK)
def store_job(job_data: JobCreate, db: Session = Depends(get_db)):
    source = job_data.source or SUPPORTED_JOB_SOURCE
    if not is_supported_job_source(source):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {', '.join(SUPPORTED_JOB_SOURCES)} sources are supported at this time."
        )

    # 1. Validate apply_url
    if not job_data.apply_url or not job_data.apply_url.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apply URL must not be empty."
        )
    
    apply_url_clean = job_data.apply_url.strip()
    if not apply_url_clean.startswith("https://"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apply URL must start with 'https://'."
        )
        
    if not is_valid_job_url_for_source(apply_url_clean, source):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Apply URL must belong to {source}."
        )

    # 2. Validate source
    if job_data.source and not is_supported_job_source(job_data.source):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {', '.join(SUPPORTED_JOB_SOURCES)} sources are supported at this time."
        )

    # Duplicate detection by user and apply_url. Different users can match the same job.
    existing_job = db.query(Job).filter(
        Job.user_id == job_data.user_id,
        Job.apply_url == apply_url_clean
    ).first()
    if existing_job:
        description_updated = False
        if len(job_data.description or "") > len(existing_job.description or ""):
            existing_job.description = job_data.description
            description_updated = True
        if description_updated or existing_job.semantic_score is None:
            score_job_for_user(db, existing_job)
        db.commit()
        logger.info(f"Duplicate job skipped for apply_url: {apply_url_clean}")
        return {"success": True, "status": "skipped"}

    incoming_fingerprint = job_fingerprint(job_data.title, job_data.company, job_data.location)
    user_jobs = db.query(Job).filter(
        Job.user_id == job_data.user_id,
        Job.source == source
    ).all()
    for existing_user_job in user_jobs:
        if incoming_fingerprint == job_fingerprint(
            existing_user_job.title,
            existing_user_job.company,
            existing_user_job.location
        ):
            description_updated = False
            if len(job_data.description or "") > len(existing_user_job.description or ""):
                existing_user_job.description = job_data.description
                description_updated = True
            if apply_url_clean:
                existing_user_job.apply_url = apply_url_clean
            if description_updated or existing_user_job.semantic_score is None:
                score_job_for_user(db, existing_user_job)
            db.commit()
            logger.info(
                "Duplicate job skipped for user %s by title/company/location fingerprint: %s",
                job_data.user_id,
                incoming_fingerprint
            )
            return {"success": True, "status": "skipped"}

    # Verify user exists
    user = db.query(User).filter(User.id == job_data.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {job_data.user_id} not found."
        )

    # Create new job record for the requested source.
    new_job = Job(
        user_id=job_data.user_id,
        title=job_data.title,
        company=job_data.company,
        location=job_data.location,
        description=job_data.description,
        apply_url=apply_url_clean,
        source=source,
        status="Discovered",
    )
    db.add(new_job)
    db.flush()
    match_result = score_job_for_user(db, new_job)
    db.commit()
    db.refresh(new_job)
    if match_result:
        logger.info(
            "Stored and scored job '%s' at %s for user %s: %.2f%%",
            new_job.title,
            new_job.company,
            new_job.user_id,
            match_result["match_score"],
        )
    else:
        logger.warning(
            "Stored job '%s' for user %s without a score because the embedding model is unavailable.",
            new_job.title,
            new_job.user_id,
        )
    return {"success": True, "status": "stored"}

@router.post("/discover")
def discover_jobs_for_current_user(
    source: str = Body(SUPPORTED_JOB_SOURCE, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return execute_discovery_for_source(db, current_user, source)


@router.post("/refresh-all")
def refresh_all_platforms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return execute_discovery_for_source(db, current_user, "All")


@router.post("/refresh/{source}")
def refresh_one_platform(
    source: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return execute_discovery_for_source(db, current_user, source)


@router.get("/stats/platforms")
def get_platform_statistics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return platform_stats_for_user(db, current_user.id)


@router.get("/count/total")
def get_total_job_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total = apply_supported_job_filter(
        db.query(Job).filter(Job.user_id == current_user.id)
    ).count()
    return {"total": total}


@router.get("/source/{source}", response_model=List[JobResponse])
def get_jobs_by_source(
    source: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not is_supported_job_source(source):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {', '.join(SUPPORTED_JOB_SOURCES)} sources are supported at this time."
        )
    query = db.query(Job).filter(Job.user_id == current_user.id, Job.source == source)
    return rank_jobs_for_user(query).all()

@router.get("/user/{user_id}", response_model=List[JobResponse])
def get_user_jobs(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to these jobs."
        )
    prune_duplicate_jobs_for_user(db, user_id)
    rescore_jobs_for_user(db, user_id)
    query = db.query(Job).filter(Job.user_id == user_id)
    jobs = rank_jobs_for_user(apply_supported_job_filter(query)).all()
    return jobs


@router.get("/me", response_model=List[JobResponse])
def get_my_jobs(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    print("Authenticated User:", current_user.id)
    prune_duplicate_jobs_for_user(db, current_user.id)
    rescore_jobs_for_user(db, current_user.id)
    query = db.query(Job).filter(Job.user_id == current_user.id)
    jobs = rank_jobs_for_user(apply_supported_job_filter(query)).all()
    return jobs


@router.get("/all")
def get_all_jobs(db: Session = Depends(get_db)):
    return db.query(Job).all()


@router.get("/{job_id}/match-analysis", response_model=JobMatchAnalysisResponse)
def get_job_match_analysis(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    if job.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this job.",
        )

    if job.semantic_score is None:
        result = score_job_for_user(db, job)
        db.commit()
        db.refresh(job)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The Hugging Face embedding model is not available.",
            )

    breakdown = job.score_breakdown_json or {}
    explanations = breakdown.get("explanations") or {}
    return JobMatchAnalysisResponse(
        job_id=job.id,
        match_score=job.match_score,
        semantic_score=job.semantic_score,
        matched_skills=job.matched_skills or [],
        missing_skills=job.missing_skills or [],
        recommendations=breakdown.get("recommendations") or [],
        explanation=explanations.get("semantic", ""),
        model=breakdown.get("model", ""),
    )


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found."
        )
    if job.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this job."
        )
    if not is_valid_job_url_for_source(job.apply_url, job.source):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found."
        )
    return job

@router.put("/{job_id}/status")
def update_job_status(job_id: int, status_update: JobStatusUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found."
        )
    if job.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this job."
        )
    if not is_valid_job_url_for_source(job.apply_url, job.source):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only real supported-source jobs can be updated."
        )

    job.status = status_update.status
    db.commit()
    db.refresh(job)
    return {"success": True}

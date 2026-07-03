import os
import shutil
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.models.job import Job
from app.models.resume import Resume
from app.models.tailored_resume import TailoredResume
from app.models.user import User
from app.schemas.resume import ResumeResponse
from app.schemas.tailored_resume import (
    GeneratePdfRequest,
    GeneratePdfResponse,
    TailorResumeRequest,
    TailorResumeResponse,
    TailoredResumeResponse,
)
from app.auth.dependencies import get_current_user
from app.services.pdf_service import generate_resume_pdf
from app.services.candidate_profile_service import upsert_parsed_candidate_profile
from app.services.resume_tailoring_service import build_resume_url, create_tailored_resume
from app.services.email_notification_service import send_resume_ready_email
from app.utils.resume_intelligence import send_resume_intelligence_webhook
from app.utils.resume_parser import count_parsed_fields, parse_resume_text
from app.utils.resume_text import extract_resume_text

router = APIRouter()
logger = logging.getLogger("app.routes.resume")

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "uploads")
TAILORED_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "tailored_resumes")

def ensure_upload_dir():
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)
    if not os.path.exists(TAILORED_UPLOAD_DIR):
        os.makedirs(TAILORED_UPLOAD_DIR)
    os.makedirs(os.path.join(UPLOAD_DIR, "resumes"), exist_ok=True)


def process_resume_intelligence(
    resume: Resume,
    current_user: User,
    db: Session,
) -> None:
    extracted_resume = extract_resume_text(resume.file_path)
    resume_text = extracted_resume["resume_text"]
    logger.info("Extracted resume text length: %s", len(resume_text))

    if resume_text.strip():
        parsed_profile = parse_resume_text(resume_text)
        logger.info(
            "Parsed resume fields count for user %s: %s",
            current_user.id,
            count_parsed_fields(parsed_profile),
        )
        saved_profile = upsert_parsed_candidate_profile(
            db,
            current_user.id,
            parsed_profile,
        )
        logger.info(
            "Saved candidate profile keys for user %s: %s",
            current_user.id,
            sorted((saved_profile.parsed_profile_json or {}).keys()),
        )
    else:
        logger.error(
            "Resume text extraction returned no text for user %s and file %s",
            current_user.id,
            resume.file_name,
        )

    send_resume_intelligence_webhook(current_user, resume, resume_text, db)


def tailored_resume_payload(record: TailoredResume, job: Job = None) -> TailoredResumeResponse:
    job_title = record.job_title or (job.title if job else None)
    company = record.company or (job.company if job else None)
    preview_url = build_resume_url(record.id, "preview")
    download_url = record.pdf_url or build_resume_url(record.id, "download")
    return TailoredResumeResponse(
        id=record.id,
        user_id=record.user_id,
        job_id=record.job_id,
        job_title=job_title,
        company=company,
        platform=job.source if job else None,
        match_score=job.match_score if job else None,
        job_description=record.job_description or (job.description if job else None),
        tailored_resume_text=record.tailored_resume_text,
        pdf_path=record.pdf_path,
        pdf_url=record.pdf_url,
        preview_url=preview_url,
        download_url=download_url,
        original_resume_path=record.original_resume_path,
        tailored_resume_path=record.tailored_resume_path,
        original_match_score=record.original_match_score,
        tailored_match_score=record.tailored_match_score,
        improvement_score=record.improvement_score,
        before_score=record.before_score if record.before_score is not None else record.original_match_score,
        after_score=record.after_score if record.after_score is not None else record.tailored_match_score,
        improvement=record.improvement if record.improvement is not None else record.improvement_score,
        matched_keywords=record.matched_keywords or [],
        missing_keywords=record.missing_keywords or [],
        sections_modified=record.sections_modified or [],
        missing_fields=record.missing_skills or [],
        resume_used=record.resume_used or "tailored",
        recommendation=record.recommendation,
        reason=record.reason,
        confidence=record.confidence,
        missing_skills=record.missing_skills or [],
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def get_owned_tailored_resume(
    tailored_resume_id: int,
    db: Session,
    current_user: User,
) -> TailoredResume:
    record = db.query(TailoredResume).filter(TailoredResume.id == tailored_resume_id).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tailored resume not found.")
    if record.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this tailored resume.")
    return record


def ensure_pdf_file(file_path: str, missing_detail: str = "Tailored resume PDF is missing.") -> None:
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=missing_detail)
    if not file_path.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Stored resume file is not a PDF. Regenerate the resume to create a PDF download.",
        )


@router.post("/upload", response_model=ResumeResponse, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ensure_upload_dir()
    
    # 1. Validate File Extension
    filename = file.filename or "resume"
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    if ext not in ["pdf", "docx"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Only PDF and DOCX files are allowed."
        )
    
    # 2. Validate File Size
    # seek to end to measure size, then seek back to beginning using underlying SpooledTemporaryFile
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    
    max_size = 10 * 1024 * 1024 # 10MB
    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds the maximum limit of 10 MB."
        )
        
    # 3. Create unique file path
    save_filename = f"user_{current_user.id}_resume.{ext}"
    file_path = os.path.join(UPLOAD_DIR, save_filename)
    
    # 4. Save file to disk
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not save file to disk: {str(e)}"
        )
        
    # 5. Save/Update record in database
    existing_resume = db.query(Resume).filter(Resume.user_id == current_user.id).first()
    
    if existing_resume:
        # Delete old file if path/name changed
        if existing_resume.file_path != file_path and os.path.exists(existing_resume.file_path):
            try:
                os.remove(existing_resume.file_path)
            except Exception:
                pass # skip if already deleted or locked
                
        existing_resume.file_name = filename
        existing_resume.file_path = file_path
        existing_resume.file_type = file.content_type or f"application/{ext}"
        existing_resume.file_size = file_size
        existing_resume.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing_resume)

        process_resume_intelligence(existing_resume, current_user, db)
        
        return existing_resume
    else:
        new_resume = Resume(
            user_id=current_user.id,
            file_name=filename,
            file_path=file_path,
            file_type=file.content_type or f"application/{ext}",
            file_size=file_size
        )
        db.add(new_resume)
        db.commit()
        db.refresh(new_resume)

        process_resume_intelligence(new_resume, current_user, db)
        
        return new_resume

@router.get("/me", response_model=ResumeResponse)
def get_my_resume(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    resume = db.query(Resume).filter(Resume.user_id == current_user.id).first()
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No resume uploaded yet."
        )
    return resume


@router.delete("/delete")
def delete_my_resume(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    resume = db.query(Resume).filter(Resume.user_id == current_user.id).first()
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No resume found to delete."
        )
        
    # Remove file from disk
    if os.path.exists(resume.file_path):
        try:
            os.remove(resume.file_path)
        except Exception as e:
            # log the error but still proceed to delete from database
            print(f"Failed to delete file from disk: {e}")
            
    db.delete(resume)
    db.commit()
    
    return {"message": "Resume deleted successfully"}


@router.post("/tailor", response_model=TailorResumeResponse)
def tailor_resume(
    request: TailorResumeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    record = create_tailored_resume(db, request, current_user)
    payload = tailored_resume_payload(record)
    try:
        send_resume_ready_email(
            to_email=current_user.email,
            name=current_user.name,
            job_title=payload.job_title or "Selected Role",
            company=payload.company or "Selected Company",
            ats_score=payload.after_score if payload.after_score is not None else "Ready",
            download_url=payload.download_url or payload.pdf_url or "",
            db=db,
            user_id=current_user.id,
        )
    except Exception as exc:
        logger.warning("Resume ready email failed for user %s: %s", current_user.id, exc)
    return {
        "success": True,
        "message": "Resume generated successfully",
        "resume_id": record.id,
        "pdf_url": payload.pdf_url or "",
        "preview_url": payload.preview_url or "",
        "download_url": payload.download_url or "",
        "tailored_resume_text": payload.tailored_resume_text or "",
        "before_score": payload.before_score,
        "after_score": payload.after_score,
        "improvement": payload.improvement,
        "resume_used": payload.resume_used,
        "reason": payload.reason,
        "confidence": payload.confidence,
        "missing_fields": payload.missing_fields,
        "generated_at": record.created_at,
        "tailored_resume": payload,
    }


@router.post("/generate-pdf", response_model=GeneratePdfResponse)
def generate_pdf(
    request: GeneratePdfRequest,
    db: Session = Depends(get_db),
):
    if request.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id is required when generating a PDF.",
        )

    user = db.query(User).filter(User.id == request.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    try:
        result = generate_resume_pdf(user.id, request.html)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"PDF generation failed for user {user.id}: {exc}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="PDF generation failed.") from exc

    # Standalone PDF generation retains its generated-file URL contract.
    generated_url = build_generated_pdf_url(result["file_name"])
    return GeneratePdfResponse(
        pdf_url=generated_url,
        preview_url=generated_url,
        download_url=generated_url,
        file_name=result["file_name"],
        file_size=result["file_size"],
        pdf_path=result["pdf_path"],
    )


@router.get("/tailored", response_model=list[TailoredResumeResponse])
def get_tailored_resume_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    records = db.query(TailoredResume).filter(
        TailoredResume.user_id == current_user.id
    ).order_by(TailoredResume.created_at.desc()).all()
    job_ids = [record.job_id for record in records if record.job_id]
    jobs = {
        job.id: job
        for job in db.query(Job).filter(Job.id.in_(job_ids)).all()
    } if job_ids else {}
    return [tailored_resume_payload(record, jobs.get(record.job_id)) for record in records]


@router.get("/tailored/job/{job_id}", response_model=TailoredResumeResponse)
def get_tailored_resume_for_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    if job.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this job.")

    record = db.query(TailoredResume).filter(
        TailoredResume.user_id == job.user_id,
        TailoredResume.job_id == job_id,
    ).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tailoring results are not ready yet.")
    return tailored_resume_payload(record, job)


def build_generated_pdf_url(file_name: str) -> str:
    from app.services.resume_tailoring_service import BASE_API_URL

    return f"{BASE_API_URL}/api/resume/generated/{file_name}/download"


@router.get("/generated/{file_name}/download")
def download_generated_resume_pdf(
    file_name: str,
    current_user: User = Depends(get_current_user),
):
    expected_prefix = f"resume_{current_user.id}_"
    if "/" in file_name or "\\" in file_name or not file_name.startswith(expected_prefix) or not file_name.endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this PDF.")

    file_path = os.path.join(UPLOAD_DIR, "resumes", file_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated resume PDF is missing.")

    return FileResponse(path=file_path, filename=file_name, media_type="application/pdf")


@router.get("/tailored/{tailored_resume_id}/preview")
def preview_tailored_resume_pdf(
    tailored_resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    record = get_owned_tailored_resume(tailored_resume_id, db, current_user)
    ensure_pdf_file(record.pdf_path)
    return FileResponse(path=record.pdf_path, filename=os.path.basename(record.pdf_path), media_type="application/pdf")


@router.get("/tailored/{tailored_resume_id}/download")
def download_tailored_resume_pdf(
    tailored_resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    record = get_owned_tailored_resume(tailored_resume_id, db, current_user)
    ensure_pdf_file(record.pdf_path)
    filename = f"tailored_resume_{tailored_resume_id}.pdf"
    return FileResponse(path=record.pdf_path, filename=filename, media_type="application/pdf")


@router.get("/tailored/{tailored_resume_id}/download/{version}")
def download_tailored_resume_file(
    tailored_resume_id: int,
    version: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    record = get_owned_tailored_resume(tailored_resume_id, db, current_user)
    if version == "original":
        file_path = record.original_resume_path
        filename = f"original_resume_job_{record.job_id}{os.path.splitext(file_path)[1]}"
    elif version == "tailored":
        file_path = record.pdf_path or record.tailored_resume_path
        filename = f"tailored_resume_{record.id}{os.path.splitext(file_path or '.pdf')[1]}"
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Download version must be original or tailored.")

    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume PDF is missing.")

    return FileResponse(path=file_path, filename=filename, media_type="application/octet-stream")

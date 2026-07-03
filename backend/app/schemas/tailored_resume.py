from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class TailorResumeRequest(BaseModel):
    job_id: Optional[int] = Field(None, description="Existing job to tailor against")
    job_title: Optional[str] = Field(None, description="Job title to tailor against")
    company: Optional[str] = Field(None, description="Company name")
    job_description: Optional[str] = Field(None, description="Detailed job description")

    @model_validator(mode="after")
    def validate_job_source(self):
        if self.job_id is None and not (self.job_title and self.company and self.job_description):
            raise ValueError("Provide job_id or job_title, company, and job_description.")
        return self


class GeneratePdfRequest(BaseModel):
    user_id: Optional[int] = None
    html: str


class GeneratePdfResponse(BaseModel):
    pdf_url: str
    preview_url: str
    download_url: str
    file_name: str
    file_size: int
    pdf_path: str


class TailoredResumeResponse(BaseModel):
    id: int
    user_id: int
    job_id: Optional[int] = None
    job_title: Optional[str] = None
    company: Optional[str] = None
    platform: Optional[str] = None
    match_score: Optional[float] = None
    job_description: Optional[str] = None
    tailored_resume_text: Optional[str] = None
    pdf_path: Optional[str] = None
    pdf_url: Optional[str] = None
    preview_url: Optional[str] = None
    download_url: Optional[str] = None
    original_resume_path: Optional[str] = None
    tailored_resume_path: Optional[str] = None
    original_match_score: Optional[float] = None
    tailored_match_score: Optional[float] = None
    improvement_score: Optional[float] = None
    before_score: Optional[float] = None
    after_score: Optional[float] = None
    improvement: Optional[float] = None
    matched_keywords: List[str] = Field(default_factory=list)
    missing_keywords: List[str] = Field(default_factory=list)
    sections_modified: List[str] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)
    resume_used: Optional[str] = None
    recommendation: Optional[str] = None
    reason: Optional[str] = None
    confidence: Optional[float] = None
    missing_skills: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TailorResumeResponse(BaseModel):
    success: bool
    message: str
    resume_id: int
    pdf_url: str
    preview_url: str
    download_url: str
    tailored_resume_text: str
    before_score: Optional[float] = None
    after_score: Optional[float] = None
    improvement: Optional[float] = None
    resume_used: Optional[str] = None
    reason: Optional[str] = None
    confidence: Optional[float] = None
    missing_fields: List[str] = Field(default_factory=list)
    generated_at: datetime
    tailored_resume: TailoredResumeResponse


class ResumeTailoringWebhookResult(BaseModel):
    resume_json: Dict[str, Any]

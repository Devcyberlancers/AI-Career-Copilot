from datetime import datetime
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field

class JobCreate(BaseModel):
    user_id: int
    title: str = Field(..., min_length=1, description="Job title")
    company: str = Field(..., min_length=1, description="Company name")
    location: Optional[str] = Field(None, description="Location of the job")
    description: Optional[str] = Field(None, description="Detailed description of the job")
    apply_url: Optional[str] = Field(None, description="URL to apply for the job")
    source: Optional[Literal["Naukri", "LinkedIn", "Foundit", "Wellfound", "Hirist", "Cutshort", "Indeed"]] = Field(None, description="Source platform of the job posting")
    status: Optional[str] = Field("Discovered", description="Status of the job application process")
    match_score: Optional[float] = Field(None, ge=0, le=100, description="Job matching score")

class JobStatusUpdate(BaseModel):
    status: Literal["Discovered", "Saved", "Applied", "Skipped"] = Field(..., description="Status to update the job to")

class JobResponse(BaseModel):
    id: int
    user_id: int
    title: str
    company: str
    location: Optional[str]
    description: Optional[str]
    apply_url: Optional[str]
    source: Optional[str]
    status: str
    match_score: Optional[float]
    semantic_score: Optional[float] = None
    confidence: Optional[float] = None
    matched_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    matched_tools: List[str] = Field(default_factory=list)
    missing_tools: List[str] = Field(default_factory=list)
    experience_gap: float = 0
    score_breakdown_json: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class JobMatchAnalysisResponse(BaseModel):
    job_id: int
    match_score: Optional[float] = None
    semantic_score: Optional[float] = None
    matched_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    explanation: str = ""
    model: str = ""

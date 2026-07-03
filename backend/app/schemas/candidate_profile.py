from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class CandidateProfileStore(BaseModel):
    user_id: Optional[int] = None
    parsed_profile_json: Optional[Dict[str, Any]] = None
    candidate_profile: Optional[Dict[str, Any]] = None


class CandidateProfileResponse(BaseModel):
    user_id: int
    parsed_profile_json: Dict[str, Any] = Field(default_factory=dict)
    raw_resume_text: str = ""
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    skills: list[Any] = Field(default_factory=list)
    projects: list[Any] = Field(default_factory=list)
    certifications: list[Any] = Field(default_factory=list)
    experience: list[Any] = Field(default_factory=list)
    education: list[Any] = Field(default_factory=list)
    tools: list[Any] = Field(default_factory=list)
    languages: list[Any] = Field(default_factory=list)
    years_of_experience: float = 0
    career_level: str = ""
    summary: str = ""
    updated_at: Optional[datetime] = None


class CandidateProfileStoredResponse(BaseModel):
    success: bool
    status: str
    candidate_profile: CandidateProfileResponse

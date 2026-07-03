from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field

class ProjectSchema(BaseModel):
    name: str = Field(..., description="Project Name")
    description: str = Field(..., description="Project Description")
    technologies_used: str = Field(..., description="Technologies Used")

class CertificationSchema(BaseModel):
    name: str = Field(..., description="Certification Name")
    issuing_organization: str = Field(..., description="Issuing Organization")
    year: int = Field(..., description="Year of Certification")

class ProfileBase(BaseModel):
    full_name: str
    email: EmailStr
    phone: str
    location: str
    
    desired_role: str
    years_experience: str
    current_designation: Optional[str] = None
    current_company: Optional[str] = None
    
    degree: str
    college: str
    graduation_year: int
    
    skills: List[str] = []
    projects: List[ProjectSchema] = []
    certifications: List[CertificationSchema] = []
    
    # Career Goals
    desired_job_title: str
    preferred_location: Optional[str] = None
    expected_salary: Optional[str] = None
    work_mode: str # Remote, Hybrid, Onsite
    max_applications_per_day: int = 20
    job_search_status: str = "Active" # Active, Paused

class ProfileCreate(ProfileBase):
    pass

class ProfileUpdate(ProfileBase):
    pass

class ProfileResponse(ProfileBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

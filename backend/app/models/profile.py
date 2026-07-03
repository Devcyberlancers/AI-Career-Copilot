import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON
from app.database.connection import Base

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # Personal Info
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    location = Column(String, nullable=False)
    
    # Professional Info
    desired_role = Column(String, nullable=False)
    years_experience = Column(String, nullable=False)
    current_designation = Column(String, nullable=True)
    current_company = Column(String, nullable=True)
    
    # Education
    degree = Column(String, nullable=False)
    college = Column(String, nullable=False)
    graduation_year = Column(Integer, nullable=False)
    
    # Dynamic Lists (stored as JSON strings/arrays/objects)
    skills = Column(JSON, nullable=False, default=list)
    projects = Column(JSON, nullable=False, default=list)
    certifications = Column(JSON, nullable=False, default=list)
    
    # Career Goals
    desired_job_title = Column(String, nullable=False)
    preferred_location = Column(String, nullable=True)
    expected_salary = Column(String, nullable=True)
    work_mode = Column(String, nullable=False) # Remote, Hybrid, Onsite
    max_applications_per_day = Column(Integer, default=20, nullable=False)
    job_search_status = Column(String, default="Active", nullable=False) # Active, Paused
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

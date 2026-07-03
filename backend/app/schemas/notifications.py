from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, Field


class NotificationResponse(BaseModel):
    id: int
    type: str
    title: str
    message: str
    action_url: Optional[str] = None
    metadata_json: Dict[str, Any] = Field(default_factory=dict)
    is_read: bool
    created_at: datetime
    read_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class NotificationSettingsUpdate(BaseModel):
    email_notifications: bool = True
    resume_ready: bool = True
    job_alerts: bool = True
    weekly_report: bool = True
    interview_reminder: bool = True
    security_alerts: bool = True
    marketing_emails: bool = False
    application_updates: bool = True


class NotificationSettingsResponse(NotificationSettingsUpdate):
    id: int
    user_id: int
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApplicationSettingsUpdate(BaseModel):
    mode: str = Field(default="manual", pattern="^(manual|automatic)$")
    auto_apply_enabled: bool = False
    minimum_match_score: float = Field(default=85, ge=0, le=100)
    preferred_companies: List[str] = Field(default_factory=list)
    preferred_locations: List[str] = Field(default_factory=list)
    salary_range: Dict[str, Any] = Field(default_factory=dict)
    experience_range: Dict[str, Any] = Field(default_factory=dict)
    remote_only: bool = False
    exclude_companies: List[str] = Field(default_factory=list)
    maximum_daily_applications: int = Field(default=5, ge=0, le=100)
    working_hours: Dict[str, Any] = Field(default_factory=dict)
    daily_job_search_enabled: bool = False
    daily_job_search_time: str = "09:00"
    daily_job_search_platforms: List[str] = Field(default_factory=list)
    jobs_per_platform: int = Field(default=20, ge=1, le=50)


class ApplicationSettingsResponse(ApplicationSettingsUpdate):
    id: int
    user_id: int
    updated_at: datetime

    model_config = {"from_attributes": True}


class EmailLogResponse(BaseModel):
    id: int
    to_email: str
    subject: str
    template_name: Optional[str] = None
    provider: str
    status: str
    attempts: int
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TestEmailRequest(BaseModel):
    to_email: Optional[EmailStr] = None
    template_name: str = "welcome"


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=6)


class VerifyEmailRequest(BaseModel):
    token: str


class LimitsResponse(BaseModel):
    platform: str
    used: int
    limit: int
    remaining: int
    reset_at: datetime


class PlatformLimitUpdate(BaseModel):
    daily_search_limit: int = Field(default=20, ge=0, le=500)
    daily_application_limit: int = Field(default=5, ge=0, le=100)
    is_enabled: bool = True

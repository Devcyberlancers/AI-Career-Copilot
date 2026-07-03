from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _object_list(value: Any, default_key: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        value = [value]

    normalized: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            normalized.append(item)
        elif str(item).strip():
            normalized.append({default_key: str(item).strip()})
    return normalized


class ResumeModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ContactInformation(ResumeModel):
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""
    location: str = ""


class EducationEntry(ResumeModel):
    institution: str = ""
    degree: str = ""
    field_of_study: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    graduation_date: str = ""
    details: list[str] = Field(default_factory=list)

    @field_validator("details", mode="before")
    @classmethod
    def normalize_details(cls, value: Any) -> list[str]:
        return _string_list(value)


class ExperienceEntry(ResumeModel):
    company: str = ""
    title: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    bullets: list[str] = Field(default_factory=list)

    @field_validator("bullets", mode="before")
    @classmethod
    def normalize_bullets(cls, value: Any) -> list[str]:
        return _string_list(value)


class ProjectEntry(ResumeModel):
    name: str = ""
    role: str = ""
    date: str = ""
    url: str = ""
    technologies: list[str] = Field(default_factory=list)
    description: str = ""
    bullets: list[str] = Field(default_factory=list)

    @field_validator("technologies", mode="before")
    @classmethod
    def normalize_technologies(cls, value: Any) -> list[str]:
        return _string_list(value)

    @field_validator("bullets", mode="before")
    @classmethod
    def normalize_bullets(cls, value: Any) -> list[str]:
        return _string_list(value)


class ResearchEntry(ResumeModel):
    title: str = ""
    publication: str = ""
    date: str = ""
    url: str = ""
    description: str = ""
    bullets: list[str] = Field(default_factory=list)

    @field_validator("bullets", mode="before")
    @classmethod
    def normalize_bullets(cls, value: Any) -> list[str]:
        return _string_list(value)


class CertificationEntry(ResumeModel):
    name: str = ""
    issuer: str = ""
    date: str = ""
    credential_id: str = ""
    url: str = ""


class TechnicalSkills(ResumeModel):
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    ai_ml: list[str] = Field(default_factory=list)
    automation: list[str] = Field(default_factory=list)
    cloud: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)

    @field_validator(
        "languages",
        "frameworks",
        "ai_ml",
        "automation",
        "cloud",
        "tools",
        mode="before",
    )
    @classmethod
    def normalize_skill_list(cls, value: Any) -> list[str]:
        return _string_list(value)


class ResumeSchema(ResumeModel):
    name: str = Field(min_length=1)
    headline: str = ""
    contact: ContactInformation = Field(default_factory=ContactInformation)
    summary: str = ""
    education: list[EducationEntry] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    research: list[ResearchEntry] = Field(default_factory=list)
    certifications: list[CertificationEntry] = Field(default_factory=list)
    technical_skills: TechnicalSkills = Field(default_factory=TechnicalSkills)
    missing_fields: list[str] = Field(default_factory=list)

    @field_validator("education", mode="before")
    @classmethod
    def normalize_education(cls, value: Any) -> list[dict[str, Any]]:
        return _object_list(value, "institution")

    @field_validator("experience", mode="before")
    @classmethod
    def normalize_experience(cls, value: Any) -> list[dict[str, Any]]:
        return _object_list(value, "company")

    @field_validator("projects", mode="before")
    @classmethod
    def normalize_projects(cls, value: Any) -> list[dict[str, Any]]:
        return _object_list(value, "name")

    @field_validator("research", mode="before")
    @classmethod
    def normalize_research(cls, value: Any) -> list[dict[str, Any]]:
        return _object_list(value, "title")

    @field_validator("certifications", mode="before")
    @classmethod
    def normalize_certifications(cls, value: Any) -> list[dict[str, Any]]:
        return _object_list(value, "name")

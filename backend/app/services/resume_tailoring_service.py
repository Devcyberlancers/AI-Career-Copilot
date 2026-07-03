import logging
import copy
import os
import json
import re
import time
from typing import Any, Dict, Optional

import requests
from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.candidate_profile import CandidateProfile
from app.models.job import Job
from app.models.resume import Resume
from app.models.resume_schema import ResumeSchema
from app.models.tailored_resume import TailoredResume
from app.models.user import User
from app.repositories.tailored_resume_repository import TailoredResumeRepository
from app.schemas.tailored_resume import TailorResumeRequest
from app.services.ats_scoring_service import calculate_ats_score
from app.services.candidate_profile_service import get_or_rebuild_candidate_profile
from app.services.pdf_service import generate_resume_pdf
from app.services.job_description_analysis import analyze_job_description
from app.services.resume_comparator import compare_resume_quality
from app.services.resume_generation_config import ACTION_VERBS
from app.services.resume_json_validator import first_words, validate_resume_json
from app.services.resume_renderer import render_resume

logger = logging.getLogger("app.services.resume_tailoring")

RESUME_TAILORING_WEBHOOK_URL = os.getenv("RESUME_TAILORING_WEBHOOK_URL", "")
BASE_API_URL = os.getenv("BASE_API_URL", "http://127.0.0.1:8001").rstrip("/")
N8N_VERIFY_SSL = os.getenv("N8N_VERIFY_SSL", "true").strip().lower() not in {"0", "false", "no", "off"}


def build_compact_groq_system_prompt() -> str:
    return (
        "Return ONLY valid JSON for the existing ResumeSchema. No markdown, HTML, CSS, tables, or explanations.\n"
        "Use candidate_profile, target_job, source_facts, total_experience_months only.\n"
        "Facts: every number, metric, tool, company, title, and date MUST appear verbatim in source_facts. If absent, omit it.\n"
        "Role title: use target_job.title. Under 12 months => Junior [Role]. 12+ months => [Role]. Never auto-add Senior/Lead/Manager.\n"
        "Summary template: [Role] with [X] months of internship experience in [top 3 tools from candidate skills]. "
        "[One achievement sentence using only source_facts metrics]. [One cross-functional value sentence from candidate_profile].\n"
        "Bullets:\n"
        "1. One sentence, max 25 words.\n"
        "2. Start with a past-tense action verb.\n"
        "3. No two bullets in the same entry share first 3 words.\n"
        "4. Do not include the entry's own project/role name.\n"
        "5. Include metrics only from source_facts.\n"
        "6. Active voice only.\n"
        "Preserve companies, dates, education, certifications, project facts, and verified achievements."
    )


def build_resume_url(tailored_resume_id: int, action: str) -> str:
    return f"{BASE_API_URL}/api/resume/tailored/{tailored_resume_id}/{action}"


def get_candidate_profile_or_404(db: Session, user_id: int) -> CandidateProfile:
    profile = get_or_rebuild_candidate_profile(db, user_id)
    if not profile or not profile.parsed_profile_json:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate profile is not ready. Upload and parse a resume before tailoring.",
        )
    return profile


def get_resume_or_404(db: Session, user_id: int) -> Resume:
    resume = db.query(Resume).filter(Resume.user_id == user_id).first()
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload your master resume before tailoring.",
        )
    return resume


def resolve_job(db: Session, request: TailorResumeRequest, current_user: User) -> Job:
    if request.job_id is not None:
        job = db.query(Job).filter(Job.id == request.job_id, Job.user_id == current_user.id).first()
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
        return job

    job = Job(
        user_id=current_user.id,
        title=request.job_title or "Target Role",
        company=request.company or "Target Company",
        description=request.job_description or "",
        source="Manual",
        status="Saved",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _json_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _list_value(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [value]


def _candidate_skills_count(candidate_profile: Dict[str, Any]) -> int:
    values: list[Any] = []
    values.extend(_list_value(candidate_profile.get("skills")))
    values.extend(_list_value(candidate_profile.get("tools")))
    technical_skills = candidate_profile.get("technical_skills")
    if isinstance(technical_skills, dict):
        for skill_group in technical_skills.values():
            values.extend(_list_value(skill_group))
    return len({str(item).strip().lower() for item in values if str(item).strip()})


def build_job_payload(job: Job) -> Dict[str, Any]:
    skills = []
    skills.extend(_list_value(job.matched_skills))
    skills.extend(_list_value(job.missing_skills))
    skills.extend(_list_value(job.matched_tools))
    skills.extend(_list_value(job.missing_tools))
    normalized_skills = []
    seen = set()
    for skill in skills:
        text = str(skill).strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            normalized_skills.append(text)

    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "employment_type": getattr(job, "employment_type", None),
        "experience_required": getattr(job, "experience_required", None),
        "salary": getattr(job, "salary", None),
        "skills": normalized_skills,
        "description": job.description or "",
        "requirements": getattr(job, "requirements", None) or job.description or "",
        "responsibilities": getattr(job, "responsibilities", None) or "",
        "preferred_skills": _list_value(getattr(job, "preferred_skills", None)),
        "source": job.source,
        "apply_url": job.apply_url,
        "posted_at": _json_value(getattr(job, "posted_at", None)),
        "status": job.status,
        "match_score": job.match_score,
        "semantic_score": job.semantic_score,
        "matched_skills": job.matched_skills or [],
        "missing_skills": job.missing_skills or [],
        "matched_tools": job.matched_tools or [],
        "missing_tools": job.missing_tools or [],
        "experience_gap": job.experience_gap,
        "score_breakdown_json": job.score_breakdown_json or {},
        "created_at": _json_value(job.created_at),
        "updated_at": _json_value(job.updated_at),
    }


def _unique_payload_list(value: Any) -> list[Any]:
    values = _list_value(value)
    deduped: list[Any] = []
    seen = set()
    for item in values:
        key = json.dumps(item, sort_keys=True, default=str) if isinstance(item, (dict, list)) else str(item)
        normalized_key = key.strip().lower()
        if normalized_key and normalized_key not in seen:
            seen.add(normalized_key)
            deduped.append(item)
    return deduped


def _estimate_token_count(value: Any) -> int:
    text = json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value or "")
    return len(re.findall(r"\b[\w+#.\-/]+\b", text))


def _strip_empty_profile_fields(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            cleaned_item = _strip_empty_profile_fields(item)
            if cleaned_item in (None, "", [], {}):
                continue
            cleaned[key] = cleaned_item
        return cleaned
    if isinstance(value, list):
        cleaned_list = [_strip_empty_profile_fields(item) for item in value]
        return [item for item in cleaned_list if item not in (None, "", [], {})]
    if isinstance(value, str):
        return " ".join(value.split())
    return value


def _numbered_lines(values: Any, *, max_items: int = 4, max_words: int = 25) -> str:
    lines: list[str] = []
    for item in _unique_payload_list(values)[:max_items]:
        text = " ".join(str(item or "").split()).strip(" -\t")
        if not text:
            continue
        words = text.split()
        if len(words) > max_words:
            text = " ".join(words[:max_words]).rstrip(" ,;:-")
        lines.append(_ensure_sentence_punctuation(text))
    return "\n".join(f"{index}. {line}" for index, line in enumerate(lines, start=1))


def _flatten_skill_categories(value: Any) -> Dict[str, str]:
    if isinstance(value, dict):
        categories = value
    else:
        categories = {"skills": value}
    flattened: Dict[str, str] = {}
    for category, values in categories.items():
        skills = _dedupe_texts(_text_list(values))[:18]
        if skills:
            flattened[str(category)] = ", ".join(skills)
    return flattened


def _compact_contact(profile: Dict[str, Any]) -> Dict[str, str]:
    contact_source = profile.get("contact") if isinstance(profile.get("contact"), dict) else {}
    contact = {
        "email": _first_nonempty(profile.get("email"), contact_source.get("email")),
        "phone": _first_nonempty(profile.get("phone"), profile.get("mobile"), contact_source.get("phone")),
        "location": _first_nonempty(profile.get("location"), contact_source.get("location")),
        "linkedin": _first_nonempty(profile.get("linkedin"), profile.get("linkedin_url"), contact_source.get("linkedin")),
        "github": _first_nonempty(profile.get("github"), profile.get("github_url"), contact_source.get("github")),
    }
    return {key: " ".join(str(value).split()) for key, value in contact.items() if str(value or "").strip()}


def _compact_profile_entries(entries: Any, *, kind: str, max_entries: int = 4) -> list[Dict[str, Any]]:
    compact_entries: list[Dict[str, Any]] = []
    for entry in _unique_payload_list(entries)[:max_entries]:
        if not isinstance(entry, dict):
            text = " ".join(str(entry or "").split())
            if text:
                compact_entries.append({"name": text} if kind == "certification" else {"details": _numbered_lines([text], max_items=1)})
            continue
        if kind == "experience":
            compact = {
                "title": _first_nonempty(entry.get("title"), entry.get("role")),
                "company": _first_nonempty(entry.get("company"), entry.get("organization")),
                "dates": _first_nonempty(
                    entry.get("dates"),
                    entry.get("duration"),
                    entry.get("period"),
                    " - ".join(item for item in _text_list((entry.get("start_date"), entry.get("end_date"))) if item.lower() != "none"),
                ),
                "location": entry.get("location"),
                "bullets": _numbered_lines(_entry_bullets(entry), max_items=4),
            }
        elif kind == "project":
            compact = {
                "name": _first_nonempty(entry.get("name"), entry.get("title")),
                "technologies": ", ".join(_dedupe_texts([*_text_list(entry.get("technologies")), *_text_list(entry.get("tech_stack")), *_text_list(entry.get("tools"))])[:10]),
                "bullets": _numbered_lines(_entry_bullets(entry), max_items=4),
            }
        elif kind == "education":
            compact = {
                "degree": _first_nonempty(entry.get("degree"), entry.get("title")),
                "institution": entry.get("institution"),
                "dates": _first_nonempty(entry.get("dates"), entry.get("year"), entry.get("graduation_date"), entry.get("end_date")),
                "score": _first_nonempty(entry.get("gpa"), entry.get("cgpa"), entry.get("grade"), entry.get("percentage")),
            }
        else:
            compact = {
                "name": _first_nonempty(entry.get("name"), entry.get("title")),
                "issuer": _first_nonempty(entry.get("issuer"), entry.get("issuing_organization")),
                "date": _first_nonempty(entry.get("date"), entry.get("year")),
            }
        compact_entries.append(_strip_empty_profile_fields(compact))
    return [entry for entry in compact_entries if entry]


def compress_profile(parsed_profile_json: Dict[str, Any]) -> Dict[str, Any]:
    profile = copy.deepcopy(parsed_profile_json or {})
    before_tokens = _estimate_token_count(profile)
    skills_source = profile.get("technical_skills") if isinstance(profile.get("technical_skills"), dict) else profile.get("skills")
    compact = {
        "name": profile.get("name"),
        "headline": profile.get("headline") or profile.get("career_level"),
        "contact": _compact_contact(profile),
        "summary": profile.get("summary"),
        "skills": _flatten_skill_categories(skills_source),
        "tools": ", ".join(_dedupe_texts(_text_list(profile.get("tools")))[:18]),
        "experience": _compact_profile_entries(profile.get("experience"), kind="experience", max_entries=4),
        "projects": _compact_profile_entries(profile.get("projects"), kind="project", max_entries=4),
        "education": _compact_profile_entries(profile.get("education"), kind="education", max_entries=2),
        "certifications": _compact_profile_entries(profile.get("certifications"), kind="certification", max_entries=5),
        "languages": ", ".join(_dedupe_texts(_text_list(profile.get("languages")))[:8]),
    }
    compact = _strip_empty_profile_fields(compact)
    while _estimate_token_count(compact) > 800:
        reduced = False
        for section in ("experience", "projects"):
            for entry in compact.get(section, []) or []:
                bullets = str(entry.get("bullets") or "").splitlines()
                if len(bullets) > 2:
                    entry["bullets"] = "\n".join(bullets[:2])
                    reduced = True
        if reduced:
            continue
        if len(compact.get("projects", []) or []) > 2:
            compact["projects"] = compact["projects"][:2]
            continue
        if len(compact.get("experience", []) or []) > 3:
            compact["experience"] = compact["experience"][:3]
            continue
        break
    after_tokens = _estimate_token_count(compact)
    logger.info("Compressed candidate profile tokens: before=%s after=%s", before_tokens, after_tokens)
    return compact


def _build_lightweight_candidate(candidate_profile: Dict[str, Any]) -> Dict[str, Any]:
    candidate_source = copy.deepcopy(candidate_profile or {})
    return {
        "name": candidate_source.get("name"),
        "headline": candidate_source.get("headline"),
        "summary": candidate_source.get("summary"),
        "skills": _unique_payload_list(candidate_source.get("skills")),
        "experience": _unique_payload_list(candidate_source.get("experience")),
        "projects": _unique_payload_list(candidate_source.get("projects")),
        "education": _unique_payload_list(candidate_source.get("education")),
        "certifications": _unique_payload_list(candidate_source.get("certifications")),
        "languages": _unique_payload_list(candidate_source.get("languages")),
    }


def _build_lightweight_job(job_payload: Dict[str, Any]) -> Dict[str, Any]:
    job = job_payload or {}
    return {
        "title": job.get("title"),
        "company": job.get("company"),
        "location": job.get("location"),
        "description": job.get("description"),
    }


def _build_lightweight_job_analysis(job_analysis: Dict[str, Any]) -> Dict[str, Any]:
    job_analysis = job_analysis or {}
    return {
        "required_skills": job_analysis.get("required_skills", []),
        "preferred_skills": job_analysis.get("preferred_skills", []),
        "required_technologies": job_analysis.get("required_technologies", []),
        "keywords": job_analysis.get("keywords", []),
    }


def _build_lightweight_tailoring_strategy() -> Dict[str, str]:
    return {
        "target_accuracy": "89-90%",
        "preserve_original_resume": "90-95%",
    }


def _walk_values(value: Any) -> list[Any]:
    values: list[Any] = []
    if isinstance(value, dict):
        for item in value.values():
            values.extend(_walk_values(item))
    elif isinstance(value, list):
        for item in value:
            values.extend(_walk_values(item))
    else:
        values.append(value)
    return values


def _extract_numeric_values(text: Any) -> list[str]:
    return re.findall(r"\b\d+(?:\.\d+)?%?\b", str(text or ""))


def _extract_date_values(text: Any) -> list[str]:
    value = str(text or "")
    matches = re.findall(
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}\b|\b(?:19|20)\d{2}\b|\bPresent\b|\bCurrent\b",
        value,
        flags=re.IGNORECASE,
    )
    return [" ".join(match.split()) for match in matches if str(match).strip()]


def _collect_tools_from_profile(parsed_profile_json: Dict[str, Any]) -> list[str]:
    tools: list[Any] = []
    for key in ("skills", "tools", "languages"):
        tools.extend(_list_value(parsed_profile_json.get(key)))
    technical = parsed_profile_json.get("technical_skills")
    if isinstance(technical, dict):
        for values in technical.values():
            tools.extend(_list_value(values))
    for project in parsed_profile_json.get("projects", []) or []:
        if isinstance(project, dict):
            tools.extend(_list_value(project.get("technologies")))
            tools.extend(_list_value(project.get("tech_stack")))
            tools.extend(_list_value(project.get("tools")))
    return _dedupe_texts([str(tool).strip() for tool in tools if str(tool).strip()])


def extract_source_facts(parsed_profile_json: Dict[str, Any]) -> Dict[str, list[str]]:
    profile = parsed_profile_json or {}
    metrics = _dedupe_texts(
        metric
        for value in _walk_values(profile)
        for metric in _extract_numeric_values(value)
    )
    dates = _dedupe_texts(
        date
        for value in _walk_values(profile)
        for date in _extract_date_values(value)
    )
    companies = []
    titles = []
    for entry in profile.get("experience", []) or []:
        if not isinstance(entry, dict):
            continue
        companies.extend(_text_list(entry.get("company")))
        companies.extend(_text_list(entry.get("organization")))
        titles.extend(_text_list(entry.get("title")))
        titles.extend(_text_list(entry.get("role")))
    return {
        "metrics": metrics,
        "tools": _collect_tools_from_profile(profile),
        "companies": _dedupe_texts(companies),
        "dates": dates,
        "titles": _dedupe_texts(titles),
    }


def _parse_profile_date(value: Any) -> Optional[tuple[int, int]]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.lower() in {"present", "current", "now"}:
        return time.gmtime().tm_year, time.gmtime().tm_mon
    month_map = {
        "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
        "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
        "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
    }
    month_year = re.search(r"\b([A-Za-z]{3,9})\s+((?:19|20)\d{2})\b", text)
    if month_year:
        return int(month_year.group(2)), month_map.get(month_year.group(1).lower(), 1)
    year = re.search(r"\b((?:19|20)\d{2})\b", text)
    if year:
        return int(year.group(1)), 1
    return None


def compute_total_experience_months_from_profile(parsed_profile_json: Dict[str, Any]) -> int:
    explicit = (parsed_profile_json or {}).get("years_of_experience") or (parsed_profile_json or {}).get("years_experience")
    if explicit not in (None, ""):
        match = re.search(r"\d+(?:\.\d+)?", str(explicit))
        if match:
            return int(round(float(match.group(0)) * 12))
    total = 0
    for entry in (parsed_profile_json or {}).get("experience", []) or []:
        if not isinstance(entry, dict):
            continue
        start = _parse_profile_date(_first_nonempty(entry.get("start_date"), entry.get("start"), entry.get("dates"), entry.get("duration"), entry.get("period")))
        end = _parse_profile_date(_first_nonempty(entry.get("end_date"), entry.get("end"), entry.get("dates"), entry.get("duration"), entry.get("period"), "Present"))
        if start and end:
            months = (end[0] - start[0]) * 12 + (end[1] - start[1])
            if months >= 0:
                total += max(1, months)
    return total


def attach_llm_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    candidate = payload.get("candidate_profile") or {}
    target_job = _build_lightweight_job(payload.get("job") or {})
    lightweight_job_analysis = _build_lightweight_job_analysis(payload.get("job_analysis") or {})
    lightweight_tailoring_strategy = _build_lightweight_tailoring_strategy()
    source_facts = payload.get("source_facts") or {}
    total_experience_months = payload.get("total_experience_months", 0)

    payload["llm_request"] = {
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.2,
        "max_tokens": 2000,
        "response_format": {
            "type": "json_object",
        },
        "messages": [
            {
                "role": "system",
                "content": payload["groq_system_prompt"],
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "candidate_profile": candidate,
                        "target_job": target_job,
                        "job_analysis": lightweight_job_analysis,
                        "tailoring_strategy": lightweight_tailoring_strategy,
                        "source_facts": source_facts,
                        "total_experience_months": total_experience_months,
                    },
                    default=str,
                ),
            },
        ],
    }
    return payload


def build_resume_tailoring_payload(
    *,
    user: User,
    candidate_profile: CandidateProfile,
    job: Job,
) -> Dict[str, Any]:
    candidate_payload = candidate_profile.parsed_profile_json or {}
    job_payload = build_job_payload(job)
    job_analysis = analyze_job_description(job)
    source_facts = extract_source_facts(candidate_payload)
    total_experience_months = compute_total_experience_months_from_profile(candidate_payload)
    compressed_candidate_payload = compress_profile(candidate_payload)
    if not job_payload["description"].strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job description is required before tailoring a resume.",
        )

    payload = {
        "event": "resume_tailoring_requested",
        "user_id": user.id,
        "candidate_profile": compressed_candidate_payload,
        "job": _build_lightweight_job(job_payload),
        "job_analysis": _build_lightweight_job_analysis(job_analysis),
        "groq_system_prompt": build_compact_groq_system_prompt(),
        "tailoring_strategy": _build_lightweight_tailoring_strategy(),
        "source_facts": source_facts,
        "total_experience_months": total_experience_months,
    }

    attach_llm_request(payload)

    payload_size = len(json.dumps(payload, default=str))
    logger.info(
        "Resume Tailoring webhook payload ready: candidate_id=%s job_id=%s job_title=%s company=%s "
        "candidate_skills=%s job_description_length=%s payload_size=%s bytes",
        user.id,
        job.id,
        job.title,
        job.company,
        _candidate_skills_count(candidate_payload),
        len(job_payload["description"]),
        payload_size,
    )
    return payload


def extract_webhook_json(response: requests.Response) -> Dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Resume Tailoring workflow did not return JSON.",
        ) from exc

    if isinstance(data, dict):
        return data
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Resume Tailoring workflow must return a JSON object.",
    )


def call_resume_tailoring_workflow(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not RESUME_TAILORING_WEBHOOK_URL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="RESUME_TAILORING_WEBHOOK_URL is not configured.",
        )

    logger.info(
        "Sending tailoring request: user=%s job=%s company=%s jd_length=%s",
        payload["user_id"],
        payload["job"]["title"],
        payload["job"]["company"],
        len(payload["job"].get("description") or ""),
    )
    try:
        response = requests.post(
            RESUME_TAILORING_WEBHOOK_URL,
            json=payload,
            timeout=180,
            verify=N8N_VERIFY_SSL,
        )
        response.raise_for_status()
        return extract_webhook_json(response)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Resume Tailoring workflow failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Resume Tailoring workflow failed: {exc}",
        ) from exc


def validate_structured_resume(data: Dict[str, Any]) -> ResumeSchema:
    resume_json = data.get("resume_json")
    if resume_json is None:
        logger.error(
            "Resume Tailoring workflow response is missing resume_json; keys=%s",
            sorted(data.keys()),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Resume Tailoring workflow response is missing resume_json.",
        )

    try:
        return ResumeSchema.model_validate(resume_json)
    except ValidationError as exc:
        logger.error(
            "Resume Tailoring structured JSON validation failed: %s",
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Resume Tailoring workflow returned invalid resume_json.",
        ) from exc


def _allowed_source_numbers(source_facts: Dict[str, Any]) -> set[str]:
    allowed: set[str] = set()
    for value in [*(source_facts.get("metrics") or []), *(source_facts.get("dates") or [])]:
        allowed.update(_extract_numeric_values(value))
    return allowed


def _strip_hallucinated_numbers(text: str, allowed_numbers: set[str], report: Dict[str, Any], path: str) -> str:
    def replace(match: re.Match[str]) -> str:
        value = match.group(0)
        if value in allowed_numbers:
            return value
        report["hallucinated_metrics"].append({"path": path, "value": value})
        return ""

    cleaned = re.sub(r"\b\d+(?:\.\d+)?%?\b", replace, str(text or ""))
    return " ".join(cleaned.replace(" %", "%").split())


def _clean_broken_verbs(text: str) -> str:
    approved = "|".join(sorted((re.escape(verb) for verb in ACTION_VERBS), key=len, reverse=True))
    weak = r"wrote|conducted|created|made|did|worked|handled|helped|used|ran|performed|analysed|analyzed"
    if not approved:
        return text
    return re.sub(
        rf"^({approved})\s+({weak})\b\s*",
        lambda match: f"{match.group(1)} ",
        text,
        flags=re.IGNORECASE,
    )


def _trim_bullet_to_words(text: str, limit: int = 20) -> str:
    words = str(text or "").split()
    if len(words) <= limit:
        return str(text or "")
    return _ensure_sentence_punctuation(" ".join(words[:limit]).rstrip(" ,;:-"))


def _clean_resume_string_value(value: str, *, path: str, source_facts: Dict[str, Any], report: Dict[str, Any]) -> str:
    text = " ".join(str(value or "").split())
    lower_path = path.lower()
    if re.fullmatch(r"(?:19|20)\d{2}", text) and not any(token in lower_path for token in ("date", "year", "duration", "period")):
        report["broken_fields"].append({"path": path, "value": text, "reason": "year_in_non_date_field"})
        return ""
    if not any(token in lower_path for token in ("date", "year", "duration", "period")):
        text = _strip_hallucinated_numbers(text, _allowed_source_numbers(source_facts), report, path)
    return _clean_broken_verbs(text)


def _clean_strings_recursive(value: Any, *, path: str, source_facts: Dict[str, Any], report: Dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {
            key: _clean_strings_recursive(item, path=f"{path}.{key}" if path else str(key), source_facts=source_facts, report=report)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _clean_strings_recursive(item, path=f"{path}[{index}]", source_facts=source_facts, report=report)
            for index, item in enumerate(value)
        ]
    if isinstance(value, str):
        return _clean_resume_string_value(value, path=path, source_facts=source_facts, report=report)
    return value


def _clean_entry_bullets(entries: list[Dict[str, Any]], *, section: str, report: Dict[str, Any]) -> None:
    for entry_index, entry in enumerate(entries or []):
        if not isinstance(entry, dict):
            continue
        entry_name = _first_nonempty(entry.get("name"), entry.get("title"), entry.get("role"), entry.get("company"))
        used_openings: set[str] = set()
        cleaned_bullets: list[str] = []
        for bullet_index, bullet in enumerate(_text_list(entry.get("bullets"))):
            text = _ensure_sentence_punctuation(_capitalize_sentence(str(bullet or "")))
            if entry_name:
                text = re.sub(re.escape(str(entry_name)), "", text, flags=re.IGNORECASE).strip(" -:;,")
            if len(text.split()) > 25:
                text = _trim_bullet_to_words(text, limit=20)
            opening = " ".join(first_words(text, 3))
            if opening and opening in used_openings:
                report["duplicate_openings"].append({
                    "path": f"{section}[{entry_index}].bullets[{bullet_index}]",
                    "opening": opening,
                })
                parts = [part.strip() for part in re.split(r"\s*;\s*|\s*,\s*", text, maxsplit=1) if part.strip()]
                if len(parts) == 2 and len(parts[1].split()) >= 5:
                    text = _ensure_sentence_punctuation(_capitalize_sentence(parts[1]))
                    opening = " ".join(first_words(text, 3))
            if text and not any(_is_near_duplicate_text(text, existing) for existing in cleaned_bullets):
                used_openings.add(opening)
                cleaned_bullets.append(text)
        entry["bullets"] = cleaned_bullets


def _merge_orphan_experience_entries(resume_json: Dict[str, Any], report: Dict[str, Any]) -> None:
    entries = resume_json.get("experience")
    if not isinstance(entries, list):
        return
    merged_entries: list[Any] = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        if not isinstance(entry, dict):
            index += 1
            continue
        company = str(entry.get("company") or "").strip()
        next_entry = entries[index + 1] if index + 1 < len(entries) else None
        if not company and isinstance(next_entry, dict):
            next_company = str(next_entry.get("company") or "").strip()
            next_bullets = _text_list(next_entry.get("bullets"))
            if next_company and not next_bullets:
                repaired = dict(next_entry)
                repaired["title"] = _first_nonempty(
                    entry.get("title"),
                    entry.get("role"),
                    entry.get("company"),
                    repaired.get("title"),
                    repaired.get("role"),
                )
                repaired["bullets"] = _text_list(entry.get("bullets")) or _entry_bullets(entry)
                repaired["start_date"] = _first_nonempty(entry.get("start_date"), repaired.get("start_date"))
                repaired["end_date"] = _first_nonempty(entry.get("end_date"), repaired.get("end_date"))
                repaired["location"] = _first_nonempty(repaired.get("location"), entry.get("location"))
                merged_entries.append(_strip_empty_profile_fields(repaired))
                report["broken_fields"].append({
                    "path": f"experience[{index}]",
                    "reason": "merged_orphan_title_with_company_entry",
                })
                index += 2
                continue
            report["broken_fields"].append({
                "path": f"experience[{index}]",
                "reason": "dropped_orphan_experience_without_company",
            })
            index += 1
            continue
        merged_entries.append(entry)
        index += 1
    resume_json["experience"] = merged_entries


def _resume_output_word_count(resume_json: Dict[str, Any]) -> int:
    summary = str(resume_json.get("summary") or "")
    bullets: list[str] = []
    for section in ("experience", "projects", "research"):
        for entry in resume_json.get(section, []) or []:
            if isinstance(entry, dict):
                bullets.extend(_text_list(entry.get("bullets")))
    skill_text = json.dumps(resume_json.get("technical_skills") or {}, default=str)
    return len(re.findall(r"\b[\w+#.\-/]+\b", " ".join([summary, *bullets, skill_text])))


def validate_resume_output(data: Dict[str, Any], source_facts: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    resume_json = copy.deepcopy(data.get("resume_json") or {})
    report = {
        "hallucinated_metrics": [],
        "duplicate_openings": [],
        "broken_fields": [],
        "word_count": 0,
        "page_estimate": "1",
        "too_short": False,
    }
    resume_json = _clean_strings_recursive(resume_json, path="resume_json", source_facts=source_facts or {}, report=report)
    _merge_orphan_experience_entries(resume_json, report)
    for section in ("experience", "projects", "research"):
        entries = resume_json.get(section)
        if isinstance(entries, list):
            _clean_entry_bullets(entries, section=section, report=report)
    word_count = _resume_output_word_count(resume_json)
    if word_count > 600:
        for section in ("experience", "projects", "research"):
            for entry in resume_json.get(section, []) or []:
                if isinstance(entry, dict):
                    entry["bullets"] = [_trim_bullet_to_words(bullet, 20) for bullet in _text_list(entry.get("bullets"))]
        word_count = _resume_output_word_count(resume_json)
    report["word_count"] = word_count
    report["page_estimate"] = "2+" if word_count > 600 else "1"
    report["too_short"] = word_count < 400
    cleaned = dict(data)
    cleaned["resume_json"] = resume_json
    cleaned["qa_report"] = report
    if report["hallucinated_metrics"] or report["duplicate_openings"] or report["broken_fields"] or report["too_short"]:
        logger.warning("Resume output QA report: %s", report)
    return cleaned, report


def _normalize_keyword(value: Any) -> str:
    return re.sub(r"[^a-z0-9+#.\-/ ]+", " ", str(value or "").lower()).strip()


def _job_keyword_terms(job_analysis: Dict[str, Any]) -> list[str]:
    terms = []
    for key in (
        "job_title",
        "industry",
        "role",
        "required_skills",
        "preferred_skills",
        "required_technologies",
        "technologies",
        "tools",
        "certifications",
        "responsibilities",
        "soft_skills",
        "keywords",
    ):
        value = job_analysis.get(key) or []
        if isinstance(value, str):
            value = [value]
        for item in value:
            normalized = _normalize_keyword(item)
            if normalized and normalized not in terms:
                terms.append(normalized)
    return terms[:60]


def _dedupe_texts(values: list[Any]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        text = str(value or "").strip()
        key = _normalize_keyword(text)
        if text and key and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _clean_contact_value(value: Any) -> str:
    text = " ".join(str(value or "").split()).strip()
    mailto_match = re.search(r"\[([^\]]+)\]\(mailto:[^)]+\)", text, re.IGNORECASE)
    if mailto_match:
        return mailto_match.group(1).strip()
    return text


def _extract_email(text: str) -> str:
    match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or "")
    return match.group(0) if match else ""


def _extract_phone(text: str) -> str:
    match = re.search(r"(?:\+?\d[\s-]?){10,14}", text or "")
    return " ".join(match.group(0).split()) if match else ""


def _extract_url(text: str, domain: str) -> str:
    pattern = rf"(?:https?://)?(?:www\.)?{re.escape(domain)}[^\s,)>\]]+"
    match = re.search(pattern, text or "", re.IGNORECASE)
    return match.group(0).rstrip(".,;") if match else ""


def _merge_contact_data(data: Dict[str, Any], original: ResumeSchema, candidate_profile: Dict[str, Any]) -> None:
    contact = dict(data.get("contact") or {})
    original_contact = original.contact.model_dump()
    raw_resume_text = candidate_profile.get("raw_resume_text", "")
    fallbacks = {
        "email": _clean_contact_value(
            _first_nonempty(
                contact.get("email"),
                original_contact.get("email"),
                candidate_profile.get("email"),
                _extract_email(raw_resume_text),
            )
        ),
        "phone": _clean_contact_value(
            _first_nonempty(
                contact.get("phone"),
                original_contact.get("phone"),
                candidate_profile.get("phone"),
                candidate_profile.get("mobile"),
                _extract_phone(raw_resume_text),
            )
        ),
        "linkedin": _clean_contact_value(
            _first_nonempty(
                contact.get("linkedin"),
                original_contact.get("linkedin"),
                candidate_profile.get("linkedin"),
                candidate_profile.get("linkedin_url"),
                _extract_url(raw_resume_text, "linkedin.com"),
            )
        ),
        "github": _clean_contact_value(
            _first_nonempty(
                contact.get("github"),
                original_contact.get("github"),
                candidate_profile.get("github"),
                candidate_profile.get("github_url"),
                _extract_url(raw_resume_text, "github.com"),
            )
        ),
        "location": _clean_contact_value(
            _first_nonempty(
                contact.get("location"),
                original_contact.get("location"),
                candidate_profile.get("location"),
            )
        ),
    }
    data["contact"] = fallbacks


def _split_terms(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,;|/\n]|\s{2,}", value)
        return [part.strip(" -•\t") for part in parts if part.strip(" -•\t")]
    if isinstance(value, (list, tuple, set)):
        result = []
        for item in value:
            result.extend(_split_terms(item))
        return result
    return [str(value).strip()] if str(value).strip() else []


def _extract_job_list_terms(text: str) -> list[str]:
    known_terms = {
        "python", "sql", "power bi", "tableau", "excel", "bigquery", "mysql",
        "postgresql", "mongodb", "aws", "azure", "gcp", "docker", "kubernetes",
        "fastapi", "django", "flask", "react", "node.js", "java", "javascript",
        "typescript", "machine learning", "statistics", "analytics", "etl",
        "airflow", "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch",
        "spark", "snowflake", "databricks", "looker", "looker studio", "dax",
        "n8n", "api", "rest", "git", "linux", "jira", "agile",
    }
    lowered = (text or "").lower()
    found = [term for term in known_terms if term in lowered]
    found.extend(_split_terms(text)[:30])
    return _dedupe_texts(found)


def build_enhanced_job_analysis(job: Job, base_analysis: Dict[str, Any]) -> Dict[str, Any]:
    job_payload = build_job_payload(job)
    description = job_payload.get("description") or ""
    full_text = " ".join(
        str(item or "")
        for item in (
            job_payload.get("title"),
            job_payload.get("company"),
            job_payload.get("location"),
            job_payload.get("requirements"),
            job_payload.get("responsibilities"),
            description,
            " ".join(_split_terms(job_payload.get("skills"))),
            " ".join(_split_terms(job_payload.get("preferred_skills"))),
        )
    )
    lower_text = full_text.lower()
    years_match = re.search(r"(\d+)\+?\s*(?:years|yrs)", lower_text)
    education_terms = [
        term for term in (
            "computer science", "engineering", "bachelor", "master", "b.e",
            "b.tech", "statistics", "mathematics", "data science"
        )
        if term in lower_text
    ]
    certification_terms = [
        term for term in (
            "aws certified", "azure certified", "google certified", "pl-300",
            "power bi certification", "tableau certification", "certification"
        )
        if term in lower_text
    ]
    technology_terms = _dedupe_texts([
        *_split_terms(job_payload.get("skills")),
        *_split_terms(job_payload.get("preferred_skills")),
        *_split_terms(base_analysis.get("required_technologies")),
        *_extract_job_list_terms(full_text),
    ])
    responsibilities = _dedupe_texts([
        *_split_terms(job_payload.get("responsibilities")),
        *_split_terms(base_analysis.get("responsibilities")),
    ])

    enhanced = {
        **base_analysis,
        "job_title": job_payload.get("title") or base_analysis.get("role") or "",
        "role": base_analysis.get("role") or job_payload.get("title") or "",
        "industry": base_analysis.get("industry") or "",
        "responsibilities": responsibilities[:14],
        "required_skills": _dedupe_texts([
            *_split_terms(base_analysis.get("required_skills")),
            *_split_terms(job_payload.get("skills")),
            *technology_terms[:12],
        ])[:18],
        "preferred_skills": _dedupe_texts([
            *_split_terms(base_analysis.get("preferred_skills")),
            *_split_terms(job_payload.get("preferred_skills")),
        ])[:14],
        "technologies": technology_terms[:24],
        "required_technologies": _dedupe_texts([
            *_split_terms(base_analysis.get("required_technologies")),
            *technology_terms,
        ])[:24],
        "tools": [term for term in technology_terms if term.lower() in {
            "power bi", "tableau", "excel", "looker", "looker studio", "git",
            "docker", "linux", "jira", "n8n", "aws", "azure", "gcp",
        }][:14],
        "certifications": certification_terms,
        "education_requirements": education_terms,
        "experience_level": base_analysis.get("experience_level") or (f"{years_match.group(1)}+ years" if years_match else ""),
        "keywords": _dedupe_texts([
            *_split_terms(base_analysis.get("keywords")),
            *technology_terms,
            *_split_terms(job_payload.get("title")),
        ])[:40],
    }
    logger.info(
        "Enhanced JD analysis: role=%s technologies=%s responsibilities=%s education_terms=%s certifications=%s",
        enhanced.get("role"),
        len(enhanced.get("technologies") or []),
        len(enhanced.get("responsibilities") or []),
        len(enhanced.get("education_requirements") or []),
        len(enhanced.get("certifications") or []),
    )
    return enhanced


def _score_text_for_job(text: str, keywords: list[str]) -> int:
    normalized_text = _normalize_keyword(text)
    score = 0
    for keyword in keywords:
        if not keyword:
            continue
        if keyword in normalized_text:
            score += 4 if " " in keyword else 2
        else:
            keyword_tokens = [token for token in keyword.split() if len(token) > 2]
            score += sum(1 for token in keyword_tokens if token in normalized_text)
    return score


def _select_job_relevant_items(items: list[Dict[str, Any]], keywords: list[str], max_items: int) -> list[Dict[str, Any]]:
    items = _dedupe_entries(items, ("company", "title", "name", "role", "start_date", "end_date", "date"))
    if len(items) <= max_items:
        return items
    ranked = sorted(
        enumerate(items),
        key=lambda pair: (
            _score_text_for_job(json.dumps(pair[1], default=str), keywords),
            -pair[0],
        ),
        reverse=True,
    )
    return [item for _, item in ranked[:max_items]]


def _make_resume_line_concise(text: str, max_chars: int = 220, max_words: int = 42) -> str:
    text = " ".join(str(text or "").split())
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words]).rstrip(" ,;:-")
        if text and text[-1] not in ".!?":
            text = f"{text}."
    if len(text) <= max_chars:
        return text

    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if sentence.strip()
    ]
    if sentences and len(sentences[0]) <= max_chars:
        return sentences[0]

    trimmed = text[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return f"{trimmed}."


def _dedupe_entries(items: list[Dict[str, Any]], keys: tuple[str, ...]) -> list[Dict[str, Any]]:
    selected: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        identity = " ".join(_normalize_keyword(item.get(key, "")) for key in keys if item.get(key)).strip()
        if not identity:
            identity = _normalize_keyword(json.dumps(item, default=str))
        if identity in seen:
            continue
        seen.add(identity)
        selected.append(item)
    return selected


def _is_low_value_bullet(text: str) -> bool:
    normalized = _normalize_keyword(text)
    weak_phrases = (
        "responsible for",
        "worked on",
        "helped with",
        "involved in",
        "various tasks",
        "different activities",
        "etc",
    )
    return len(normalized) < 35 or any(phrase in normalized for phrase in weak_phrases)


SIMILARITY_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "the",
    "to",
    "using",
    "via",
    "with",
}

DUPLICATE_FILLER_WORDS = {
    "achieved",
    "across",
    "aligned",
    "analysis",
    "analyze",
    "analyzed",
    "analysed",
    "applied",
    "automated",
    "built",
    "created",
    "delivered",
    "designed",
    "developed",
    "enabled",
    "executed",
    "generated",
    "identified",
    "improved",
    "optimized",
    "performed",
    "prepared",
    "provided",
    "reduced",
    "supported",
    "used",
    "utilized",
    "leveraged",
    "implemented",
    "conducted",
    "made",
    "worked",
    "helped",
    "role",
    "team",
    "business",
    "project",
    "solution",
    "system",
    "data",
}


def _similarity_tokens(text: str) -> set[str]:
    normalized = _normalize_keyword(text)
    return {
        token
        for token in normalized.split()
        if len(token) > 2 and token not in SIMILARITY_STOP_WORDS
    }


def _duplicate_signature_tokens(text: str) -> set[str]:
    tokens = set()
    for token in _similarity_tokens(text):
        if token in DUPLICATE_FILLER_WORDS:
            continue
        token = re.sub(r"(ing|ed|es|s)$", "", token)
        if len(token) > 2:
            tokens.add(token)
    return tokens


def _has_same_core_meaning(left: str, right: str) -> bool:
    left_tokens = _duplicate_signature_tokens(left)
    right_tokens = _duplicate_signature_tokens(right)
    if len(left_tokens) < 4 or len(right_tokens) < 4:
        return False
    overlap = len(left_tokens & right_tokens)
    smaller = min(len(left_tokens), len(right_tokens))
    union = len(left_tokens | right_tokens)
    return (overlap / smaller) >= 0.72 or (overlap / union) >= 0.58


def _is_near_duplicate_text(left: str, right: str) -> bool:
    left_key = _normalize_keyword(left)
    right_key = _normalize_keyword(right)
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    if min(len(left_key), len(right_key)) >= 55 and (left_key in right_key or right_key in left_key):
        return True
    if _leading_signature(left_key) and _leading_signature(left_key) == _leading_signature(right_key):
        return True
    if _has_same_core_meaning(left_key, right_key):
        return True

    left_tokens = _similarity_tokens(left_key)
    right_tokens = _similarity_tokens(right_key)
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    smaller = min(len(left_tokens), len(right_tokens))
    return (overlap / union) >= 0.9 or (overlap / smaller) >= 0.96


def _bullet_quality_score(text: str, keywords: Optional[list[str]] = None) -> tuple[int, int, int, int]:
    normalized = _normalize_keyword(text)
    keyword_score = _score_text_for_job(text, keywords or [])
    metric_score = 1 if re.search(r"\d+%|\d+\+?|\b(reduced|improved|automated|optimized|increased|decreased|delivered|built|designed|identified)\b", text, re.I) else 0
    action_score = 1 if re.match(r"^(built|designed|developed|automated|analyzed|analysed|implemented|optimized|improved|delivered|created|extracted|performed|integrated)\b", normalized) else 0
    return keyword_score, metric_score, action_score, len(text)


def _dedupe_similar_texts(values: list[str], keywords: Optional[list[str]] = None) -> list[str]:
    selected: list[str] = []
    for value in values or []:
        text = " ".join(str(value or "").split())
        if not text:
            continue
        duplicate_index = next(
            (index for index, existing in enumerate(selected) if _is_near_duplicate_text(text, existing)),
            None,
        )
        if duplicate_index is None:
            selected.append(text)
            continue
        if _bullet_quality_score(text, keywords) > _bullet_quality_score(selected[duplicate_index], keywords):
            selected[duplicate_index] = text
    return selected


def _dedupe_sentence_text(text: str, keywords: Optional[list[str]] = None) -> str:
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", str(text or ""))
        if sentence.strip()
    ]
    if len(sentences) <= 1:
        return " ".join(str(text or "").split())
    return " ".join(_dedupe_similar_texts(sentences, keywords))


def _leading_signature(text: str) -> str:
    normalized = _normalize_keyword(text)
    if not normalized:
        return ""
    first_clause = re.split(r"\s*(?:;|,|\band\b|\bwhile\b|\bto\b)\s+", normalized, maxsplit=1)[0]
    tokens = [token for token in first_clause.split() if token not in SIMILARITY_STOP_WORDS]
    return " ".join(tokens[:7])


def _capitalize_sentence(text: str) -> str:
    text = text.strip(" ;,.")
    if not text:
        return text
    return f"{text[0].upper()}{text[1:]}"


def _remove_repeated_bullet_openers(bullets: list[str]) -> list[str]:
    signatures: set[str] = set()
    cleaned: list[str] = []
    for bullet in bullets or []:
        text = " ".join(str(bullet or "").split())
        signature = _leading_signature(text)
        if signature and signature in signatures:
            parts = [
                part.strip()
                for part in re.split(r"\s*;\s*", text, maxsplit=1)
                if part.strip()
            ]
            if len(parts) == 2 and len(parts[1].split()) >= 6:
                text = _capitalize_sentence(parts[1])
            else:
                comma_parts = [
                    part.strip()
                    for part in re.split(r"\s*,\s*", text, maxsplit=1)
                    if part.strip()
                ]
                if len(comma_parts) == 2 and len(comma_parts[1].split()) >= 6:
                    text = _capitalize_sentence(comma_parts[1])
        signature = _leading_signature(text)
        if signature:
            signatures.add(signature)
        cleaned.append(text)
    return cleaned


def _select_job_relevant_bullets(bullets: list[str], keywords: list[str], max_bullets: int = 4) -> list[str]:
    cleaned = []
    for bullet in bullets or []:
        text = _make_resume_line_concise(str(bullet).strip(), max_chars=220, max_words=42)
        if text and not _is_low_value_bullet(text):
            cleaned.append(text)
    cleaned = _dedupe_similar_texts(cleaned, keywords)
    if not cleaned:
        cleaned = _dedupe_similar_texts(
            [_make_resume_line_concise(str(bullet).strip()) for bullet in bullets[:max_bullets] if str(bullet).strip()],
            keywords,
        )
    if len(cleaned) <= max_bullets:
        return _remove_repeated_bullet_openers(cleaned)
    ranked = sorted(
        enumerate(cleaned),
        key=lambda pair: (_score_text_for_job(pair[1], keywords), -pair[0]),
        reverse=True,
    )
    return _remove_repeated_bullet_openers([bullet for _, bullet in ranked[:max_bullets]])


def _bullet_limit_for_section(section: str) -> int:
    if section == "projects":
        return 4
    if section == "research":
        return 2
    return 4


def _entry_identity(entry: Dict[str, Any], keys: tuple[str, ...]) -> str:
    values = [_normalize_keyword(entry.get(key, "")) for key in keys]
    return " ".join(value for value in values if value).strip()


def _find_matching_entry(
    entry: Dict[str, Any],
    candidates: list[Dict[str, Any]],
    keys: tuple[str, ...],
) -> Optional[Dict[str, Any]]:
    identity = _entry_identity(entry, keys)
    if not identity:
        return None
    identity_tokens = {token for token in identity.split() if len(token) > 2}
    best_match = None
    best_overlap = 0
    for candidate in candidates:
        candidate_identity = _entry_identity(candidate, keys)
        candidate_tokens = {token for token in candidate_identity.split() if len(token) > 2}
        overlap = len(identity_tokens & candidate_tokens)
        if overlap > best_overlap:
            best_overlap = overlap
            best_match = candidate
    return best_match if best_overlap else None


def _merge_bullet_lists(
    primary: list[str],
    secondary: list[str],
    keywords: list[str],
    max_bullets: int = 3,
) -> list[str]:
    combined = []
    for bullet in [*primary, *secondary]:
        text = _make_resume_line_concise(bullet, max_chars=220, max_words=42)
        if text and not _is_low_value_bullet(text):
            combined.append(text)
    combined = _dedupe_similar_texts(combined, keywords)
    return _select_job_relevant_bullets(combined, keywords, max_bullets=max_bullets)


def _merge_skill_groups(
    primary: Dict[str, Any],
    secondary: Dict[str, Any],
    keywords: list[str],
) -> Dict[str, Any]:
    merged = dict(primary or {})
    for key, values in (secondary or {}).items():
        primary_values = _text_list(merged.get(key))
        secondary_values = _text_list(values)
        merged[key] = _rank_skill_values([*primary_values, *secondary_values], keywords, max_items=10)
    for key, values in list(merged.items()):
        if isinstance(values, list):
            merged[key] = _rank_skill_values(values, keywords, max_items=10)
    return merged


def enrich_structured_resume_density(
    tailored_resume: ResumeSchema,
    original_resume: ResumeSchema,
    job_analysis: Dict[str, Any],
) -> ResumeSchema:
    keywords = _job_keyword_terms(job_analysis)
    tailored = tailored_resume.model_dump()
    original = original_resume.model_dump()

    if len((tailored.get("summary") or "").split()) < 18 and original.get("summary"):
        tailored["summary"] = original["summary"]

    tailored["technical_skills"] = _merge_skill_groups(
        tailored.get("technical_skills") or {},
        original.get("technical_skills") or {},
        keywords,
    )

    for section, keys, max_items in (
        ("experience", ("company", "title"), 3),
        ("projects", ("name", "role"), 4),
        ("research", ("title", "publication"), 1),
    ):
        tailored_entries = list(tailored.get(section) or [])
        original_entries = list(original.get(section) or [])
        enriched_entries = []

        for entry in tailored_entries:
            match = _find_matching_entry(entry, original_entries, keys)
            source_bullets = (match or {}).get("bullets", []) if match else []
            if not source_bullets and match:
                source_bullets = _entry_bullets(match)
            entry["bullets"] = _merge_bullet_lists(
                entry.get("bullets", []),
                source_bullets,
                keywords,
                max_bullets=_bullet_limit_for_section(section),
            )
            if section == "projects":
                entry["technologies"] = _rank_skill_values(
                    [*_text_list(entry.get("technologies")), *_text_list((match or {}).get("technologies"))],
                    keywords,
                    max_items=8,
                )
            enriched_entries.append(entry)

        existing_identities = {
            _entry_identity(entry, keys)
            for entry in enriched_entries
            if _entry_identity(entry, keys)
        }
        for entry in _select_job_relevant_items(original_entries, keywords, max_items=max_items):
            identity = _entry_identity(entry, keys)
            if identity and identity in existing_identities:
                continue
            entry["bullets"] = _select_job_relevant_bullets(
                entry.get("bullets", []) or _entry_bullets(entry),
                keywords,
                max_bullets=_bullet_limit_for_section(section),
            )
            enriched_entries.append(entry)
            if len(enriched_entries) >= max_items:
                break

        tailored[section] = _select_job_relevant_items(enriched_entries, keywords, max_items=max_items)

    if len(tailored.get("education") or []) < 1 and original.get("education"):
        tailored["education"] = original["education"][:1]
    if len(tailored.get("certifications") or []) < 3 and original.get("certifications"):
        combined_certs = [*(tailored.get("certifications") or []), *(original.get("certifications") or [])]
        tailored["certifications"] = _select_job_relevant_items(combined_certs, keywords, max_items=4)

    enriched = ResumeSchema.model_validate(tailored)
    logger.info(
        "Enriched resume density from original profile: experience=%s projects=%s skills_groups=%s certifications=%s",
        len(enriched.experience),
        len(enriched.projects),
        len([value for value in enriched.technical_skills.model_dump().values() if value]),
        len(enriched.certifications),
    )
    return enriched


def _trim_summary(summary: str) -> str:
    sentences = [
        item.strip()
        for item in re.split(r"(?<=[.!?])\s+", summary or "")
        if item.strip()
    ]
    if not sentences:
        return ""
    return _make_summary_text(sentences, max_sentences=4, max_chars=720, max_words=125)


def _make_summary_text(
    sentences: list[str],
    *,
    max_sentences: int = 4,
    max_chars: int = 720,
    max_words: int = 125,
) -> str:
    selected: list[str] = []
    total_words = 0
    total_chars = 0
    for sentence in sentences:
        text = _ensure_sentence_punctuation(
            _make_resume_line_concise(sentence, max_chars=280, max_words=46)
        )
        words = len(text.split())
        if selected and (total_words + words > max_words or total_chars + len(text) > max_chars):
            break
        selected.append(text)
        total_words += words
        total_chars += len(text) + 1
        if len(selected) >= max_sentences:
            break
    return " ".join(selected)


def _rank_skill_values(values: list[str], keywords: list[str], max_items: int = 10) -> list[str]:
    if len(values or []) <= max_items:
        return _dedupe_texts(values or [])
    ranked = sorted(
        enumerate(_dedupe_texts(values)),
        key=lambda pair: (_score_text_for_job(pair[1], keywords), -pair[0]),
        reverse=True,
    )
    return [value for _, value in ranked[:max_items]]


def _resume_search_text(resume: ResumeSchema) -> str:
    return json.dumps(resume.model_dump(), default=str)


def compare_resume_to_job(resume: ResumeSchema, job_analysis: Dict[str, Any]) -> Dict[str, Any]:
    resume_text = _normalize_keyword(_resume_search_text(resume))
    keywords = _job_keyword_terms(job_analysis)
    matched = []
    missing = []
    for keyword in keywords:
        if keyword and keyword in resume_text:
            matched.append(keyword)
        elif keyword:
            missing.append(keyword)
    coverage = round((len(matched) / len(keywords)) * 100, 2) if keywords else 100.0
    relevant_experience = sorted(
        resume.experience,
        key=lambda entry: _score_text_for_job(json.dumps(entry.model_dump(), default=str), keywords),
        reverse=True,
    )
    relevant_projects = sorted(
        resume.projects,
        key=lambda entry: _score_text_for_job(json.dumps(entry.model_dump(), default=str), keywords),
        reverse=True,
    )
    relevant_certifications = sorted(
        resume.certifications,
        key=lambda entry: _score_text_for_job(json.dumps(entry.model_dump(), default=str), keywords),
        reverse=True,
    )
    return {
        "matched_skills": matched,
        "missing_skills": missing,
        "keyword_coverage": coverage,
        "semantic_match": min(100.0, coverage + min(10, len(relevant_experience) * 2 + len(relevant_projects))),
        "relevant_experience": relevant_experience,
        "relevant_projects": relevant_projects,
        "relevant_certifications": relevant_certifications,
    }


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _numeric_years_from_profile(candidate_profile: Dict[str, Any]) -> Optional[float]:
    for key in ("years_of_experience", "years_experience", "experience_years"):
        value = candidate_profile.get(key)
        if value in (None, ""):
            continue
        match = re.search(r"\d+(?:\.\d+)?", str(value))
        if match:
            return float(match.group(0))
    raw_text = candidate_profile.get("raw_resume_text", "")
    match = re.search(r"(\d+(?:\.\d+)?)\+?\s*(?:years|yrs)", raw_text or "", re.IGNORECASE)
    return float(match.group(1)) if match else None


def _profile_looks_entry_level(candidate_profile: Dict[str, Any]) -> bool:
    raw_text = str(candidate_profile.get("raw_resume_text") or "")
    experience = candidate_profile.get("experience") or []
    experience_text = json.dumps(experience, default=str)
    combined = f"{raw_text} {experience_text}"
    return bool(re.search(r"\b(intern|internship|fresher|entry level|entry-level|trainee)\b", combined, re.IGNORECASE))


def _credible_role_for_profile(role: str, candidate_profile: Dict[str, Any]) -> str:
    role = re.split(r"\s+\|\s+|,", str(role or ""))[0].strip()
    years = _numeric_years_from_profile(candidate_profile)
    if (years is not None and years < 3) or _profile_looks_entry_level(candidate_profile):
        role = re.sub(r"\b(senior|sr\.?|lead|principal|staff)\b\s*", "", role, flags=re.IGNORECASE).strip()
    if not role:
        role = "Data Analyst"
    return " ".join(role.split())


def _years_from_profile(candidate_profile: Dict[str, Any]) -> str:
    numeric_years = _numeric_years_from_profile(candidate_profile)
    if numeric_years is not None:
        if numeric_years < 1:
            return "hands-on internship"
        if numeric_years.is_integer():
            return f"{int(numeric_years)}+ years"
        return f"{numeric_years:g} years"
    for key in ("years_of_experience", "years_experience", "experience_years"):
        value = candidate_profile.get(key)
        if value not in (None, ""):
            return f"{value}+ years" if str(value).isdigit() else str(value)
    raw_text = candidate_profile.get("raw_resume_text", "")
    match = re.search(r"(\d+)\+?\s*(?:years|yrs)", raw_text or "", re.IGNORECASE)
    return f"{match.group(1)}+ years" if match else ""


def _top_resume_terms(resume: ResumeSchema, job_analysis: Dict[str, Any], max_terms: int = 5) -> list[str]:
    keywords = _job_keyword_terms(job_analysis)
    technical = resume.technical_skills.model_dump()
    values = []
    for key in ("languages", "frameworks", "ai_ml", "automation", "cloud", "tools"):
        values.extend(_text_list(technical.get(key)))
    for project in resume.projects:
        values.extend(project.technologies)
    ranked = _rank_skill_values(values, keywords, max_items=max_terms)
    return ranked[:max_terms]


def _headline_terms(resume: ResumeSchema, job_analysis: Dict[str, Any], max_terms: int = 5) -> list[str]:
    low_signal_terms = {
        "excel", "git", "github", "linux", "vs code", "vscode", "pandas",
        "numpy", "matplotlib", "seaborn", "plotly", "jupyter", "anaconda",
    }
    preferred_order = _dedupe_texts([
        *_split_terms(job_analysis.get("required_technologies")),
        *_split_terms(job_analysis.get("technologies")),
        *_split_terms(job_analysis.get("required_skills")),
        *_split_terms(job_analysis.get("preferred_skills")),
        *_split_terms(job_analysis.get("tools")),
    ])
    technical = resume.technical_skills.model_dump()
    supported = []
    for key in ("languages", "frameworks", "ai_ml", "automation", "cloud", "tools"):
        supported.extend(_text_list(technical.get(key)))
    for project in resume.projects:
        supported.extend(project.technologies)

    supported_text = _normalize_keyword(" ".join(supported))
    selected = []
    for term in preferred_order:
        normalized = _normalize_keyword(term)
        if not normalized or normalized in low_signal_terms:
            continue
        if normalized in supported_text and normalized not in {_normalize_keyword(item) for item in selected}:
            selected.append(term)
        if len(selected) >= max_terms:
            break

    if len(selected) < 3:
        for term in _top_resume_terms(resume, job_analysis, max_terms=10):
            normalized = _normalize_keyword(term)
            if normalized and normalized not in low_signal_terms and normalized not in {_normalize_keyword(item) for item in selected}:
                selected.append(term)
            if len(selected) >= max_terms:
                break
    return selected[:max_terms]


def _impact_phrase(resume: ResumeSchema) -> str:
    bullets = []
    for entry in [*resume.experience, *resume.projects]:
        bullets.extend(getattr(entry, "bullets", []) or [])
    metric_bullets = [
        bullet for bullet in bullets
        if re.search(r"\d+%|\d+\+?|\b(reduced|improved|automated|optimized|increased|decreased|delivered)\b", bullet, re.IGNORECASE)
    ]
    if metric_bullets:
        return _make_resume_line_concise(metric_bullets[0], max_chars=120, max_words=18)
    return ""


def build_tailored_headline(
    resume: ResumeSchema,
    candidate_profile: Dict[str, Any],
    job_analysis: Dict[str, Any],
) -> str:
    role = _first_nonempty(job_analysis.get("role"), job_analysis.get("job_title"), resume.headline, candidate_profile.get("career_level"))
    role = _credible_role_for_profile(role, candidate_profile)
    terms = _headline_terms(resume, job_analysis, max_terms=5)
    while terms:
        headline = f"{role} | {' | '.join(terms)}" if role else " | ".join(terms)
        if len(headline) <= 90:
            return headline
        terms = terms[:-1]
    return _make_resume_line_concise(role or "ATS-Optimized Candidate", max_chars=90, max_words=10)


def build_tailored_summary(
    resume: ResumeSchema,
    candidate_profile: Dict[str, Any],
    job_analysis: Dict[str, Any],
) -> str:
    role = _first_nonempty(job_analysis.get("role"), job_analysis.get("job_title"), resume.headline, candidate_profile.get("career_level"), "Professional")
    role = _credible_role_for_profile(role, candidate_profile)
    years = _years_from_profile(candidate_profile)
    terms = _headline_terms(resume, job_analysis, max_terms=5) or _top_resume_terms(resume, job_analysis, max_terms=5)
    impact = _impact_phrase(resume)
    parts = []
    lead = f"{role} with {years} experience" if years else f"{role} with hands-on experience"
    if terms:
        lead += f" across {', '.join(terms)}"
    parts.append(lead)
    if impact:
        parts.append(_capitalize_sentence(impact))
    else:
        parts.append("Focused on translating business requirements into measurable, production-ready outcomes.")
    responsibilities = _split_terms(job_analysis.get("responsibilities"))[:2]
    if responsibilities:
        parts.append(f"Aligned to roles requiring {', '.join(responsibilities)}.")
    summary_sentences = _summary_sentences(_dedupe_sentence_text(" ".join(parts), _job_keyword_terms(job_analysis)))
    return _make_summary_text(summary_sentences, max_sentences=4, max_chars=720, max_words=125)


def _skill_category_for_keyword(keyword: str) -> str:
    normalized = _normalize_keyword(keyword)
    languages = {
        "c",
        "c++",
        "c#",
        "java",
        "javascript",
        "python",
        "r",
        "sql",
        "typescript",
    }
    databases = {
        "bigquery",
        "mongodb",
        "mysql",
        "postgres",
        "postgresql",
        "snowflake",
        "sql server",
        "sqlite",
    }
    ai_ml = {
        "airflow",
        "artificial intelligence",
        "deep learning",
        "machine learning",
        "matplotlib",
        "ml",
        "numpy",
        "pandas",
        "plotly",
        "scikit learn",
        "scikit-learn",
        "seaborn",
        "tensorflow",
        "pytorch",
    }
    frameworks = {
        "django",
        "express",
        "fastapi",
        "flask",
        "node js",
        "node.js",
        "react",
        "springboot",
    }
    cloud = {
        "aws",
        "azure",
        "docker",
        "gcp",
        "google cloud",
        "kubernetes",
    }
    automation = {
        "airflow",
        "automation",
        "github actions",
        "n8n",
        "power automate",
        "selenium",
    }

    if normalized in languages:
        return "languages"
    if normalized in databases:
        return "databases"
    if normalized in ai_ml:
        return "ai_ml"
    if normalized in frameworks:
        return "frameworks"
    if normalized in cloud:
        return "cloud"
    if normalized in automation:
        return "automation"
    return "tools"


def _merge_supported_keywords_into_skills(data: Dict[str, Any], original: ResumeSchema, job_analysis: Dict[str, Any]) -> None:
    keywords = _dedupe_texts([
        *_split_terms(job_analysis.get("required_skills")),
        *_split_terms(job_analysis.get("preferred_skills")),
        *_split_terms(job_analysis.get("required_technologies")),
        *_split_terms(job_analysis.get("technologies")),
        *_split_terms(job_analysis.get("tools")),
    ])
    original_text = _normalize_keyword(_resume_search_text(original))
    technical = data.get("technical_skills") or {}
    for keyword in keywords:
        normalized = _normalize_keyword(keyword)
        if not normalized or normalized not in original_text:
            continue
        category = _skill_category_for_keyword(keyword)
        values = _text_list(technical.get(category))
        if not any(normalized == _normalize_keyword(item) for item in values):
            values.append(keyword)
        technical[category] = values

    for category, values in list(technical.items()):
        if isinstance(values, list):
            technical[category] = _rank_skill_values(values, keywords, max_items=12)
    data["technical_skills"] = technical


def remove_duplicate_content(data: Dict[str, Any]) -> Dict[str, Any]:
    seen_bullets: list[str] = []
    for section in ("experience", "projects", "research"):
        for entry in data.get(section, []) or []:
            unique_bullets = []
            for bullet in entry.get("bullets", []) or []:
                text = " ".join(str(bullet or "").split())
                if not text:
                    continue
                duplicate_index = next(
                    (index for index, existing in enumerate(seen_bullets) if _is_near_duplicate_text(text, existing)),
                    None,
                )
                if duplicate_index is None:
                    seen_bullets.append(text)
                    unique_bullets.append(text)
                    continue
                if _bullet_quality_score(text) > _bullet_quality_score(seen_bullets[duplicate_index]):
                    seen_bullets[duplicate_index] = text
            entry["bullets"] = unique_bullets
    return data


def _ensure_sentence_punctuation(text: str) -> str:
    text = " ".join(str(text or "").split()).strip(" -•\t")
    if text and text[-1] not in ".!?":
        text = f"{text}."
    return text


def _summary_sentences(summary: str) -> list[str]:
    cleaned = re.sub(r"\bSelected impact:\s*", "", str(summary or ""), flags=re.IGNORECASE)
    return [
        _ensure_sentence_punctuation(sentence)
        for sentence in re.split(r"(?<=[.!?])\s+", cleaned)
        if sentence.strip()
    ]


def _repair_summary_text(
    resume: ResumeSchema,
    original: ResumeSchema,
    candidate_profile: Dict[str, Any],
    job_analysis: Dict[str, Any],
) -> str:
    keywords = _job_keyword_terms(job_analysis)
    sentences = _dedupe_similar_texts(_summary_sentences(resume.summary), keywords)
    sentences = [
        _make_resume_line_concise(sentence, max_chars=240, max_words=40)
        for sentence in sentences
        if sentence
    ]
    if len(sentences) < 3 or len(" ".join(sentences).split()) < 55:
        fallback = _summary_sentences(build_tailored_summary(resume, candidate_profile, job_analysis))
        sentences = _dedupe_similar_texts([*sentences, *fallback], keywords)
    if len(sentences) < 3 or len(" ".join(sentences).split()) < 55:
        fallback = _summary_sentences(build_tailored_summary(original, candidate_profile, job_analysis))
        sentences = _dedupe_similar_texts([*sentences, *fallback], keywords)
    if len(sentences) < 3 or len(" ".join(sentences).split()) < 55:
        terms = _headline_terms(resume, job_analysis, max_terms=5) or _top_resume_terms(resume, job_analysis, max_terms=5)
        responsibilities = _split_terms(job_analysis.get("responsibilities"))[:2]
        if terms:
            sentences.append(
                f"Applies {', '.join(terms)} to deliver clear analysis, automation, and decision-ready outputs for business teams."
            )
        if responsibilities:
            sentences.append(
                f"Prepared for roles focused on {', '.join(responsibilities)} while preserving verified resume experience and project impact."
            )
        sentences = _dedupe_similar_texts(sentences, keywords)
    return _make_summary_text(sentences, max_sentences=4, max_chars=720, max_words=125)


def _approved_action_verb_set() -> set[str]:
    return {str(verb).strip().lower() for verb in ACTION_VERBS if str(verb).strip()}


def _repair_bullet_action_verb(text: str, index: int = 0) -> str:
    text = _ensure_sentence_punctuation(_capitalize_sentence(re.sub(r"^[•*\-\u2022]\s*", "", str(text or ""))))
    text = _collapse_action_verb_collision(text)
    first_word = first_words(text, 1)
    if first_word and first_word[0] in _approved_action_verb_set():
        return text

    verb_pool = [verb for verb in ACTION_VERBS if str(verb).strip()]
    verb = str(verb_pool[index % len(verb_pool)] if verb_pool else "Delivered").strip()
    text = re.sub(
        r"^(wrote|conducted|created|made|did|worked|handled|helped|used)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    lowered = text[:1].lower() + text[1:] if text else "job-relevant work."
    repaired = _ensure_sentence_punctuation(f"{verb} {lowered}")
    return _collapse_action_verb_collision(repaired)


def _collapse_action_verb_collision(text: str) -> str:
    approved = "|".join(sorted((re.escape(verb) for verb in _approved_action_verb_set()), key=len, reverse=True))
    weak = r"wrote|conducted|created|made|did|worked|handled|helped|used|analysed"
    text = re.sub(r"\b(\w+)\s+\1\b", r"\1", str(text or ""), flags=re.IGNORECASE)
    if approved:
        text = re.sub(
            rf"^({approved})\s+({approved}|{weak})\b\s*",
            lambda match: f"{match.group(1)} ",
            text,
            flags=re.IGNORECASE,
        )
    return _ensure_sentence_punctuation(_capitalize_sentence(text))


def _repair_bullet_list(bullets: list[str], keywords: list[str], max_bullets: int, min_bullets: int = 0) -> list[str]:
    repaired = []
    for index, bullet in enumerate(bullets or []):
        text = _make_resume_line_concise(bullet, max_chars=220, max_words=42)
        if not text:
            continue
        repaired.append(_repair_bullet_action_verb(text, index))
    repaired = _dedupe_similar_texts(repaired, keywords)
    repaired = _remove_repeated_bullet_openers(repaired)
    if len(repaired) > max_bullets:
        repaired = _select_job_relevant_bullets(repaired, keywords, max_bullets=max_bullets)
    return repaired[:max_bullets]


def _derive_sentence_bullets_from_entry(entry: Dict[str, Any]) -> list[str]:
    source_texts = [
        *_text_list(entry.get("description")),
        *_text_list(entry.get("details")),
        *_text_list(entry.get("summary")),
        *_text_list(entry.get("bullets")),
    ]
    derived: list[str] = []
    for source in source_texts:
        text = " ".join(str(source or "").split())
        parts = [
            part.strip(" .;,-")
            for part in re.split(r"(?<=[.!?])\s+|\s*;\s*|\s+\band\s+", text)
            if len(part.strip().split()) >= 7
        ]
        for part in parts:
            candidate = _ensure_sentence_punctuation(_capitalize_sentence(part))
            if candidate and not any(_is_near_duplicate_text(candidate, existing) for existing in derived):
                derived.append(candidate)

    technologies = _dedupe_texts(
        [
            *_text_list(entry.get("technologies")),
            *_text_list(entry.get("tech_stack")),
            *_text_list(entry.get("tools")),
        ]
    )
    name = _first_nonempty(entry.get("name"), entry.get("project_name"), entry.get("title"))
    if name and technologies:
        tech_phrase = ", ".join(technologies[:5])
        candidate = _ensure_sentence_punctuation(
            f"Applied {tech_phrase} to build and improve {name}."
        )
        if not any(_is_near_duplicate_text(candidate, existing) for existing in derived):
            derived.append(candidate)

    role = _first_nonempty(entry.get("role"), entry.get("title"))
    company = _first_nonempty(entry.get("company"), entry.get("organization"))
    if role and company and technologies:
        tech_phrase = ", ".join(technologies[:4])
        candidate = _ensure_sentence_punctuation(
            f"Used {tech_phrase} in the {role} role at {company} to support role-aligned analysis and delivery."
        )
        if not any(_is_near_duplicate_text(candidate, existing) for existing in derived):
            derived.append(candidate)
    return derived


def repair_structured_resume_after_validation(
    resume: ResumeSchema,
    original: ResumeSchema,
    candidate_profile: Dict[str, Any],
    job_analysis: Dict[str, Any],
) -> ResumeSchema:
    keywords = _job_keyword_terms(job_analysis)
    data = resume.model_dump()
    current_name = " ".join(str(data.get("name") or "").split())
    fallback_name = _first_nonempty(original.name, candidate_profile.get("name"), "Candidate")
    data["name"] = fallback_name if not current_name or current_name.lower() == "candidate" else current_name
    data["headline"] = _make_resume_line_concise(
        build_tailored_headline(resume, candidate_profile, job_analysis),
        max_chars=90,
        max_words=12,
    )
    data["summary"] = _repair_summary_text(resume, original, candidate_profile, job_analysis)
    data["experience"] = _dedupe_entries(data.get("experience", []) or [], ("company", "title", "location", "start_date", "end_date"))
    data["projects"] = _dedupe_entries(data.get("projects", []) or [], ("name", "role", "date"))

    for section in ("experience", "projects", "research"):
        max_bullets = _bullet_limit_for_section(section)
        for entry in data.get(section, []) or []:
            for key, value in list(entry.items()):
                if isinstance(value, str):
                    entry[key] = " ".join(value.split())
            min_bullets = 2 if section == "experience" and entry.get("bullets") else 0
            entry["bullets"] = _repair_bullet_list(
                _text_list(entry.get("bullets")),
                keywords,
                max_bullets=max_bullets,
                min_bullets=min_bullets,
            )
            target_min = 2 if section == "experience" else 3 if section == "projects" else 0
            if target_min and len(entry["bullets"]) < target_min:
                expanded = _repair_bullet_list(
                    [*entry["bullets"], *_derive_sentence_bullets_from_entry(entry)],
                    keywords,
                    max_bullets=max_bullets,
                    min_bullets=target_min,
                )
                if len(expanded) > len(entry["bullets"]):
                    entry["bullets"] = expanded

    data["certifications"] = _dedupe_certification_entries(data.get("certifications", []))

    for edu in data.get("education", []) or []:
        edu["details"] = [
            _ensure_sentence_punctuation(_capitalize_sentence(detail))
            for detail in _dedupe_similar_texts(_text_list(edu.get("details")), keywords)
        ]

    technical = data.get("technical_skills") or {}
    for key, value in list(technical.items()):
        technical[key] = _dedupe_texts(_text_list(value))
    data["technical_skills"] = technical
    data = remove_duplicate_content(data)
    return ResumeSchema.model_validate(data)


def _clean_certification_years(text: str) -> str:
    text = " ".join(str(text or "").split())
    text = re.sub(r"\((\d{4})\)\s*\(\1\)", r"(\1)", text)
    text = re.sub(r"\b(20\d{2}|19\d{2})\s+\1\b", r"\1", text)
    return text


def _dedupe_certification_entries(entries: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    selected: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries or []:
        if not isinstance(entry, dict):
            entry = {"name": str(entry or "").strip()}
        cleaned = dict(entry)
        cleaned["name"] = _clean_certification_years(cleaned.get("name", ""))
        cleaned["issuer"] = _clean_certification_years(cleaned.get("issuer", ""))
        cleaned["date"] = _clean_certification_years(cleaned.get("date", ""))
        key = _normalize_keyword(re.sub(r"\b(20\d{2}|19\d{2})\b", "", cleaned.get("name", "")))
        compact_key = re.sub(r"[^a-z0-9+#.]+", "", key)
        if not compact_key:
            continue
        duplicate = any(
            compact_key == existing
            or (len(compact_key) >= 12 and compact_key in existing)
            or (len(existing) >= 12 and existing in compact_key)
            for existing in seen
        )
        if duplicate:
            continue
        seen.add(compact_key)
        selected.append(cleaned)
    return selected


def _supported_second_experience_bullets(entry: Dict[str, Any]) -> list[str]:
    existing = _text_list(entry.get("bullets"))
    suggestions: list[str] = []
    for bullet in existing:
        parts = [
            part.strip(" .;,-")
            for part in re.split(r"\s*;\s*|\s+\band\b\s+", bullet, maxsplit=2)
            if len(part.strip().split()) >= 7
        ]
        for part in parts[1:]:
            candidate = _capitalize_sentence(part)
            if candidate and candidate[-1] not in ".!?":
                candidate = f"{candidate}."
            suggestions.append(candidate)

    return [
        suggestion
        for suggestion in suggestions
        if not any(_is_near_duplicate_text(suggestion, existing_bullet) for existing_bullet in existing)
    ]


def _ensure_minimum_experience_depth(entry: Dict[str, Any], keywords: list[str], min_bullets: int = 2) -> None:
    bullets = _dedupe_similar_texts(_text_list(entry.get("bullets")), keywords)
    if len(bullets) >= min_bullets:
        entry["bullets"] = _remove_repeated_bullet_openers(bullets)
        return
    bullets.extend(_supported_second_experience_bullets({**entry, "bullets": bullets}))
    entry["bullets"] = _select_job_relevant_bullets(bullets, keywords, max_bullets=_bullet_limit_for_section("experience"))


def _copy_missing_experience_dates(entry: Dict[str, Any], match: Dict[str, Any]) -> None:
    if not match:
        return
    if not entry.get("start_date"):
        entry["start_date"] = _first_nonempty(
            match.get("start_date"),
            match.get("start"),
            match.get("dates"),
            match.get("duration"),
            match.get("period"),
        )
    if not entry.get("end_date"):
        entry["end_date"] = _first_nonempty(
            match.get("end_date"),
            match.get("end"),
        )
    if entry.get("start_date") and not entry.get("end_date"):
        date_text = str(entry["start_date"])
        parts = re.split(r"\s+(?:-|–|—|to)\s+", date_text, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2:
            entry["start_date"] = parts[0].strip()
            entry["end_date"] = parts[1].strip()


def validate_tailored_resume_quality(
    resume: ResumeSchema,
    original: ResumeSchema,
    candidate_profile: Dict[str, Any],
    job_analysis: Dict[str, Any],
) -> ResumeSchema:
    keywords = _job_keyword_terms(job_analysis)
    data = resume.model_dump()
    _merge_contact_data(data, original, candidate_profile)
    data["headline"] = build_tailored_headline(resume, candidate_profile, job_analysis)
    data["summary"] = _dedupe_sentence_text(
        build_tailored_summary(resume, candidate_profile, job_analysis),
        keywords,
    )

    for section in ("experience", "projects"):
        max_bullets = _bullet_limit_for_section(section)
        original_entries = original.model_dump().get(section, []) or []
        for entry in data.get(section, []) or []:
            match = _find_matching_entry(entry, original_entries, ("company", "title") if section == "experience" else ("name", "role"))
            if section == "experience":
                _copy_missing_experience_dates(entry, match or {})
            merged = _merge_bullet_lists(
                entry.get("bullets", []) or [],
                (match or {}).get("bullets", []) or _entry_bullets(match or {}),
                keywords,
                max_bullets=max_bullets,
            )
            if len(merged) < min(3, max_bullets):
                fallback = _select_job_relevant_bullets(
                    [*_entry_bullets(entry), *_entry_bullets(match or {})],
                    keywords,
                    max_bullets=max_bullets,
                )
                merged = _dedupe_similar_texts([*merged, *fallback], keywords)[:max_bullets]
            entry["bullets"] = merged
            if section == "experience":
                _ensure_minimum_experience_depth(entry, keywords, min_bullets=2)

    _merge_supported_keywords_into_skills(data, original, job_analysis)
    data = remove_duplicate_content(data)
    validated = ResumeSchema.model_validate(data)
    comparison = compare_resume_to_job(validated, job_analysis)
    logger.info(
        "Tailored resume quality check: coverage=%s matched=%s missing=%s semantic=%s",
        comparison["keyword_coverage"],
        len(comparison["matched_skills"]),
        len(comparison["missing_skills"]),
        comparison["semantic_match"],
    )
    return validated


def optimize_structured_resume_for_job(resume: ResumeSchema, job_analysis: Dict[str, Any]) -> ResumeSchema:
    keywords = _job_keyword_terms(job_analysis)
    data = resume.model_dump()

    data["summary"] = _trim_summary(data.get("summary", ""))
    data["headline"] = _make_resume_line_concise(data.get("headline", ""), max_chars=110, max_words=16)

    data["projects"] = _select_job_relevant_items(data.get("projects", []), keywords, max_items=3)
    data["experience"] = _select_job_relevant_items(data.get("experience", []), keywords, max_items=4)
    data["research"] = _select_job_relevant_items(data.get("research", []), keywords, max_items=1)
    data["education"] = _select_job_relevant_items(data.get("education", []), keywords, max_items=1)
    data["certifications"] = _select_job_relevant_items(data.get("certifications", []), keywords, max_items=4)

    for section in ("experience", "projects", "research"):
        for entry in data.get(section, []) or []:
            entry["bullets"] = _select_job_relevant_bullets(
                entry.get("bullets", []),
                keywords,
                max_bullets=_bullet_limit_for_section(section),
            )
            if entry.get("description"):
                entry["description"] = _make_resume_line_concise(entry.get("description"), max_chars=220, max_words=40)
            if entry.get("technologies") and isinstance(entry.get("technologies"), list):
                entry["technologies"] = _rank_skill_values(entry["technologies"], keywords, max_items=8)

    for entry in data.get("education", []) or []:
        entry["details"] = [
            _make_resume_line_concise(detail, max_chars=140, max_words=22)
            for detail in (entry.get("details") or [])[:2]
            if str(detail).strip()
        ]

    technical_skills = data.get("technical_skills") or {}
    for key, value in list(technical_skills.items()):
        if isinstance(value, list):
            technical_skills[key] = _rank_skill_values(value, keywords)
    data["technical_skills"] = technical_skills

    optimized = ResumeSchema.model_validate(data)
    logger.info(
        "Optimized structured resume for readable ATS output: experience=%s projects=%s keywords=%s",
        len(optimized.experience),
        len(optimized.projects),
        len(keywords),
    )
    return optimized


def calculate_original_resume_score(
    original_resume_json: Dict[str, Any],
    job_description: str,
) -> Dict[str, Any]:
    try:
        result = calculate_ats_score(original_resume_json, job_description)
        logger.info(
            "Original resume ATS score calculated: score=%s matched=%s missing=%s",
            result.get("score"),
            len(result.get("matched_keywords", [])),
            len(result.get("missing_keywords", [])),
        )
        return result
    except Exception:
        logger.exception("Original resume ATS scoring failed; resume generation will continue.")
        return {
            "score": None,
            "matched_keywords": [],
            "missing_keywords": [],
            "strengths": [],
            "recommendations": [],
        }


def calculate_tailored_resume_score(
    tailored_resume: ResumeSchema,
    job_description: str,
) -> Dict[str, Any]:
    try:
        result = calculate_ats_score(tailored_resume.model_dump(), job_description)
        logger.info(
            "Tailored resume ATS score calculated: score=%s matched=%s missing=%s",
            result.get("score"),
            len(result.get("matched_keywords", [])),
            len(result.get("missing_keywords", [])),
        )
        return result
    except Exception:
        logger.exception("Tailored resume ATS scoring failed; resume generation will continue.")
        return {
            "score": None,
            "matched_keywords": [],
            "missing_keywords": [],
            "strengths": [],
            "recommendations": [],
        }


def _text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _entry_bullets(entry: Dict[str, Any]) -> list[str]:
    bullets = []
    bullets.extend(_text_list(entry.get("bullets")))
    bullets.extend(_text_list(entry.get("details")))
    bullets.extend(_text_list(entry.get("description")))
    return bullets


def _education_details(entry: Dict[str, Any]) -> list[str]:
    details = _entry_bullets(entry)
    for key, label in (
        ("gpa", "GPA"),
        ("cgpa", "CGPA"),
        ("grade", "Grade"),
        ("coursework", "Relevant Coursework"),
        ("relevant_coursework", "Relevant Coursework"),
    ):
        value = entry.get(key)
        if value not in (None, ""):
            text = f"{label}: {value}"
            if not any(_normalize_keyword(text) == _normalize_keyword(item) for item in details):
                details.append(text)
    return details


def build_resume_schema_from_candidate_profile(candidate_profile: Dict[str, Any]) -> ResumeSchema:
    skills = _text_list(candidate_profile.get("skills"))
    tools = _text_list(candidate_profile.get("tools"))
    languages = []
    frameworks = []
    ai_ml = []
    automation = []
    cloud = []

    for skill in [*skills, *tools]:
        lowered = skill.lower()
        if lowered in {"python", "java", "javascript", "typescript", "sql", "c++", "c#", "r", "dax"}:
            languages.append(skill)
        elif lowered in {"fastapi", "react", "next.js", "nextjs", "django", "flask", "node.js", "nodejs", "express", "springboot"}:
            frameworks.append(skill)
        elif any(term in lowered for term in ("machine learning", "ai", "ml", "pytorch", "tensorflow", "nlp", "opencv", "yolo", "airflow", "scikit", "pandas", "numpy")):
            ai_ml.append(skill)
        elif any(term in lowered for term in ("n8n", "automation", "zapier", "airflow")):
            automation.append(skill)
        elif any(term in lowered for term in ("aws", "azure", "gcp", "cloud", "docker", "kubernetes")):
            cloud.append(skill)

    experience = []
    for entry in candidate_profile.get("experience", []) or []:
        if not isinstance(entry, dict):
            continue
        experience.append({
            "title": entry.get("title", ""),
            "company": entry.get("company", ""),
            "start_date": _first_nonempty(
                entry.get("start_date"),
                entry.get("start"),
                entry.get("dates"),
                entry.get("duration"),
                entry.get("period"),
            ),
            "end_date": _first_nonempty(entry.get("end_date"), entry.get("end")),
            "bullets": _entry_bullets(entry),
        })

    projects = []
    for entry in candidate_profile.get("projects", []) or []:
        if not isinstance(entry, dict):
            continue
        projects.append({
            "name": entry.get("name") or entry.get("title", ""),
            "technologies": _text_list(entry.get("technologies") or entry.get("technologies_used")),
            "description": entry.get("description", ""),
            "bullets": _entry_bullets(entry),
        })

    education = []
    for entry in candidate_profile.get("education", []) or []:
        if not isinstance(entry, dict):
            continue
        education.append({
            "institution": entry.get("institution", ""),
            "degree": entry.get("degree") or entry.get("title", ""),
            "field_of_study": entry.get("field_of_study", ""),
            "start_date": _first_nonempty(entry.get("start_date"), entry.get("start")),
            "end_date": _first_nonempty(entry.get("end_date"), entry.get("end")),
            "graduation_date": _first_nonempty(entry.get("graduation_date"), entry.get("year"), entry.get("dates")),
            "details": _education_details(entry),
        })

    certifications = []
    for entry in candidate_profile.get("certifications", []) or []:
        if isinstance(entry, dict):
            certifications.append({
                "name": entry.get("name", ""),
                "issuer": entry.get("issuer") or entry.get("issuing_organization", ""),
                "date": entry.get("date") or entry.get("year", ""),
            })
        elif str(entry).strip():
            certifications.append({"name": str(entry).strip()})

    return ResumeSchema.model_validate({
        "name": candidate_profile.get("name") or "Candidate",
        "headline": candidate_profile.get("career_level") or "",
        "contact": {
            "email": _clean_contact_value(_first_nonempty(candidate_profile.get("email"), _extract_email(candidate_profile.get("raw_resume_text", "")))),
            "phone": _clean_contact_value(_first_nonempty(candidate_profile.get("phone"), candidate_profile.get("mobile"), _extract_phone(candidate_profile.get("raw_resume_text", "")))),
            "linkedin": _clean_contact_value(_first_nonempty(candidate_profile.get("linkedin"), candidate_profile.get("linkedin_url"), _extract_url(candidate_profile.get("raw_resume_text", ""), "linkedin.com"))),
            "github": _clean_contact_value(_first_nonempty(candidate_profile.get("github"), candidate_profile.get("github_url"), _extract_url(candidate_profile.get("raw_resume_text", ""), "github.com"))),
            "location": candidate_profile.get("location", ""),
        },
        "summary": candidate_profile.get("summary") or "",
        "education": education,
        "experience": experience,
        "projects": projects,
        "certifications": certifications,
        "technical_skills": {
            "languages": languages,
            "frameworks": frameworks,
            "ai_ml": ai_ml,
            "automation": automation,
            "cloud": cloud,
            "tools": [item for item in tools if item not in languages + frameworks + ai_ml + automation + cloud],
        },
    })


def ensure_original_resume_pdf(
    user: User,
    resume: Resume,
    candidate_profile: CandidateProfile,
    job_analysis: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    logger.info(
        "Rendering compact original resume profile to ATS PDF for user %s. Uploaded file path=%s",
        user.id,
        resume.file_path,
    )
    original_resume = build_resume_schema_from_candidate_profile(candidate_profile.parsed_profile_json or {})
    if job_analysis:
        original_resume = optimize_structured_resume_for_job(original_resume, job_analysis)
        original_resume = validate_tailored_resume_quality(
            original_resume,
            original_resume,
            candidate_profile.parsed_profile_json or {},
            job_analysis,
        )
    original_html = render_resume(original_resume)
    return generate_resume_pdf(user.id, original_html)


def prepare_structured_resume_for_rendering(
    workflow_result: Dict[str, Any],
    *,
    candidate_profile_json: Dict[str, Any],
    job_analysis: Dict[str, Any],
) -> tuple[ResumeSchema, Any]:
    source_facts = extract_source_facts(candidate_profile_json)
    workflow_result, qa_report = validate_resume_output(workflow_result, source_facts)
    structured_resume = validate_structured_resume(workflow_result)
    original_resume_schema = build_resume_schema_from_candidate_profile(candidate_profile_json)
    structured_resume = enrich_structured_resume_density(
        structured_resume,
        original_resume_schema,
        job_analysis,
    )
    structured_resume = optimize_structured_resume_for_job(
        structured_resume,
        job_analysis,
    )
    structured_resume = validate_tailored_resume_quality(
        structured_resume,
        original_resume_schema,
        candidate_profile_json,
        job_analysis,
    )
    structured_resume = repair_structured_resume_after_validation(
        structured_resume,
        original_resume_schema,
        candidate_profile_json,
        job_analysis,
    )
    validation = validate_resume_json(
        structured_resume,
        candidate_profile=candidate_profile_json,
    )
    validation.qa_report = qa_report
    if not validation.valid:
        logger.info("Repairing structured resume locally after validation issues: %s", validation.violations)
        structured_resume = repair_structured_resume_after_validation(
            structured_resume,
            original_resume_schema,
            candidate_profile_json,
            job_analysis,
        )
        validation = validate_resume_json(
            structured_resume,
            candidate_profile=candidate_profile_json,
        )
        validation.qa_report = qa_report
    return structured_resume, validation


def generate_validated_structured_resume(
    workflow_payload: Dict[str, Any],
    *,
    candidate_profile_json: Dict[str, Any],
    job_analysis: Dict[str, Any],
) -> tuple[ResumeSchema, Any]:
    workflow_started = time.perf_counter()
    workflow_result = call_resume_tailoring_workflow(workflow_payload)
    logger.info("Resume Tailoring workflow result keys: %s", list(workflow_result.keys()))
    logger.info("Resume Tailoring workflow time: %.2fs", time.perf_counter() - workflow_started)

    structured_resume, validation = prepare_structured_resume_for_rendering(
        workflow_result,
        candidate_profile_json=candidate_profile_json,
        job_analysis=job_analysis,
    )
    if not validation.valid:
        validation.manual_review_required = True
        structured_resume.missing_fields = sorted(set([*structured_resume.missing_fields, *validation.missing_fields]))
        logger.warning(
            "Structured resume validation still has non-critical issues after local repair: %s",
            validation.violations,
        )
    return structured_resume, validation


def create_tailored_resume(
    db: Session,
    request: TailorResumeRequest,
    current_user: User,
) -> TailoredResume:
    start_time = time.perf_counter()
    print("Authenticated User:", current_user.id)
    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    candidate_profile = get_candidate_profile_or_404(db, current_user.id)
    resume = get_resume_or_404(db, current_user.id)
    job = resolve_job(db, request, current_user)

    logger.info(
        "Resume Tailoring candidate profile for user %s: keys=%s, raw_resume_text_length=%s",
        user.id,
        sorted((candidate_profile.parsed_profile_json or {}).keys()),
        len((candidate_profile.parsed_profile_json or {}).get("raw_resume_text", "")),
    )
    workflow_payload = build_resume_tailoring_payload(
        user=user,
        candidate_profile=candidate_profile,
        job=job,
    )
    job_analysis = build_enhanced_job_analysis(job, workflow_payload.get("job_analysis") or analyze_job_description(job))
    before_score_result = calculate_original_resume_score(
        candidate_profile.parsed_profile_json or {},
        job.description or "",
    )

    candidate_profile_json = candidate_profile.parsed_profile_json or {}
    structured_resume, quality_validation = generate_validated_structured_resume(
        workflow_payload,
        candidate_profile_json=candidate_profile_json,
        job_analysis=job_analysis,
    )
    logger.info(
        "Validated structured resume for user %s: education=%s experience=%s "
        "projects=%s research=%s certifications=%s quality_valid=%s word_count=%s",
        user.id,
        len(structured_resume.education),
        len(structured_resume.experience),
        len(structured_resume.projects),
        len(structured_resume.research),
        len(structured_resume.certifications),
        quality_validation.valid,
        quality_validation.word_count,
    )

    after_score_result = calculate_tailored_resume_score(
        structured_resume,
        job.description or "",
    )
    optimization_report = compare_resume_quality(
        before_score_result=before_score_result,
        after_score_result=after_score_result,
        original_resume_json=candidate_profile.parsed_profile_json or {},
        tailored_resume_json=structured_resume,
    )
    before_score = optimization_report["before_score"]
    after_score = optimization_report["after_score"]
    improvement = optimization_report["improvement"]
    logger.info(
        "Resume Quality Guard result: before=%s after=%s improvement=%s resume_used=%s confidence=%s",
        before_score,
        after_score,
        improvement,
        optimization_report["resume_used"],
        optimization_report["confidence"],
    )

    repository = TailoredResumeRepository(db)
    if optimization_report["resume_used"] == "original":
        logger.info(
            "Resume Quality Guard kept original content for user %s and job %s. Rendering compact ATS PDF from parsed profile.",
            user.id,
            job.id,
        )
        original_pdf_result = ensure_original_resume_pdf(user, resume, candidate_profile, job_analysis)
        record = repository.create(
            user_id=user.id,
            job_id=job.id,
            job_title=job.title,
            company=job.company,
            job_description=job.description or "",
            tailored_resume_text=original_pdf_result.get("text") or (candidate_profile.parsed_profile_json or {}).get("raw_resume_text", ""),
            pdf_path=original_pdf_result["pdf_path"],
            pdf_url="",
            original_resume_path=resume.file_path,
            before_score=before_score,
            after_score=after_score,
            improvement=improvement,
            matched_keywords=optimization_report["matched_keywords"],
            missing_keywords=optimization_report["missing_keywords"],
            sections_modified=optimization_report["sections_modified"],
            resume_used="original",
            recommendation=optimization_report["recommendation"],
            reason=(
                f"{optimization_report['reason']} Manual review recommended: {', '.join(quality_validation.violations)}"
                if quality_validation.manual_review_required else optimization_report["reason"]
            ),
            confidence=optimization_report["confidence"],
            missing_skills=quality_validation.missing_fields,
        )
        record.pdf_url = build_resume_url(record.id, "download")
        db.commit()
        db.refresh(record)
        logger.info(
            "Original resume selected successfully for user %s, job '%s' at %s, total time %.2fs",
            user.id,
            job.title,
            job.company,
            time.perf_counter() - start_time,
        )
        return record

    try:
        rendered_html = render_resume(structured_resume)
    except Exception as exc:
        logger.exception(
            "ATS resume rendering failed for user %s",
            user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ATS resume rendering failed.",
        ) from exc

    logger.info(
        "Rendered ATS resume HTML for user %s: length=%s",
        user.id,
        len(rendered_html),
    )

    pdf_started = time.perf_counter()
    try:
        pdf_result = generate_resume_pdf(user.id, rendered_html)
    except Exception as exc:
        logger.exception(
            "PDF generation failed for tailored resume user %s",
            user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tailored resume PDF generation failed.",
        ) from exc

    logger.info(f"PDF generation time: {time.perf_counter() - pdf_started:.2f}s")
    pdf_path = pdf_result["pdf_path"]
    tailored_text = pdf_result["text"]
    pdf_url = ""

    record = repository.create(
        user_id=user.id,
        job_id=job.id,
        job_title=job.title,
        company=job.company,
        job_description=job.description or "",
        tailored_resume_text=tailored_text,
        pdf_path=pdf_path,
        pdf_url=pdf_url,
        original_resume_path=resume.file_path,
        before_score=before_score,
        after_score=after_score,
        improvement=improvement,
        matched_keywords=after_score_result.get("matched_keywords", []),
        missing_keywords=after_score_result.get("missing_keywords", []),
        sections_modified=optimization_report["sections_modified"],
        resume_used="tailored",
        recommendation=optimization_report["recommendation"],
        reason=(
            f"{optimization_report['reason']} Manual review recommended: {', '.join(quality_validation.violations)}"
            if quality_validation.manual_review_required else optimization_report["reason"]
        ),
        confidence=optimization_report["confidence"],
        missing_skills=quality_validation.missing_fields,
    )

    record.pdf_url = pdf_url or build_resume_url(record.id, "download")
    db.commit()
    db.refresh(record)

    logger.info(
        f"Tailored resume generated successfully for user {user.id}, "
        f"job '{job.title}' at {job.company}, total time {time.perf_counter() - start_time:.2f}s"
    )
    return record

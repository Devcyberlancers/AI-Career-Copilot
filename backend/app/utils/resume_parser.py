import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


SECTION_ALIASES = {
    "professional summary": "summary",
    "summary": "summary",
    "profile": "summary",
    "skills": "skills",
    "technical skills": "skills",
    "core competencies": "skills",
    "work experience": "experience",
    "professional experience": "experience",
    "experience": "experience",
    "projects": "projects",
    "academic projects": "projects",
    "education": "education",
    "academic background": "education",
    "certifications": "certifications",
    "certificates": "certifications",
    "languages": "languages",
    "additional information": "additional",
    "achievements": "achievements",
    "achievements and activities": "achievements",
    "achievements & activities": "achievements",
}

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

DATE_RANGE_PATTERN = re.compile(
    r"(?P<start>(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{4}|\d{4})\s*[–—-]\s*"
    r"(?P<end>Present|Current|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
    r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}|\d{4})",
    re.IGNORECASE,
)
MONTH_YEAR_PATTERN = re.compile(
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{4}",
    re.IGNORECASE,
)
YEAR_PATTERN = re.compile(r"\b(?:19|20)\d{2}\b")


def parse_resume_text(resume_text: str) -> Dict[str, Any]:
    lines = _clean_lines(resume_text)
    sections = _split_sections(lines)
    header_lines = sections.pop("header", [])

    name = _parse_name(header_lines)
    email = _first_match(resume_text, r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
    phone = _first_match(
        resume_text,
        r"(?<!\d)(?:\+\d{1,3}[\s-]?)?(?:\(?\d{2,5}\)?[\s-]?)?\d{3,5}[\s-]?\d{4,6}(?!\d)",
    )
    location = _parse_labeled_value(header_lines, "location")

    skills, tools = _parse_skills(sections.get("skills", []))
    experience = _parse_dated_entries(sections.get("experience", []), "experience")
    projects = _parse_dated_entries(sections.get("projects", []), "project")
    education = _parse_dated_entries(sections.get("education", []), "education")
    certifications = _parse_certifications(sections.get("certifications", []))
    languages = _parse_languages(
        sections.get("languages", []) + sections.get("additional", [])
    )
    summary = " ".join(sections.get("summary", [])).strip()

    profile = {
        "name": name,
        "email": email,
        "phone": phone,
        "location": location,
        "skills": skills,
        "tools": tools,
        "projects": projects,
        "experience": experience,
        "education": education,
        "certifications": certifications,
        "languages": languages,
        "years_of_experience": _estimate_years_of_experience(
            resume_text, experience
        ),
        "career_level": _infer_career_level(resume_text, experience),
        "summary": summary,
        "raw_resume_text": resume_text.strip(),
    }
    return profile


def count_parsed_fields(profile: Dict[str, Any]) -> int:
    return sum(
        1
        for key, value in profile.items()
        if key != "raw_resume_text" and value not in ("", None, [], {})
    )


def is_debug_profile(profile: Any) -> bool:
    if not isinstance(profile, dict):
        return True
    nested = profile.get("candidate_profile")
    if isinstance(nested, dict):
        profile = nested
    meaningful_keys = {
        "name", "email", "phone", "location", "skills", "projects",
        "experience", "education", "certifications", "tools", "languages",
        "years_of_experience", "years_experience", "summary", "raw_resume_text",
    }
    return not any(key in profile and profile.get(key) not in ("", None, [], {}) for key in meaningful_keys)


def _clean_lines(text: str) -> List[str]:
    return [
        re.sub(r"\s+", " ", line).strip(" \t•")
        for line in text.replace("\r", "\n").split("\n")
        if re.sub(r"\s+", " ", line).strip(" \t•")
    ]


def _normalize_heading(line: str) -> str:
    return re.sub(r"[^a-z& ]+", "", line.lower()).strip()


def _split_sections(lines: List[str]) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {"header": []}
    current = "header"
    for line in lines:
        heading = SECTION_ALIASES.get(_normalize_heading(line))
        if heading:
            current = heading
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)
    return sections


def _parse_name(header_lines: List[str]) -> str:
    for line in header_lines[:5]:
        if ":" in line or "@" in line or "|" in line or re.search(r"\d", line):
            continue
        words = line.split()
        if 1 < len(words) <= 5:
            return line
    return header_lines[0] if header_lines else ""


def _first_match(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(0).strip() if match else ""


def _parse_labeled_value(lines: List[str], label: str) -> str:
    pattern = re.compile(rf"{re.escape(label)}\s*:\s*([^|]+)", re.IGNORECASE)
    for line in lines:
        match = pattern.search(line)
        if match:
            return match.group(1).strip()
    return ""


def _parse_skills(lines: List[str]) -> Tuple[List[str], List[str]]:
    skills: List[str] = []
    tools: List[str] = []
    tool_labels = ("tool", "platform", "database", "cloud", "infra", "bi ", "visual")
    for line in lines:
        label, separator, values = line.partition(":")
        skill_text = values if separator else line
        parsed = _split_list(skill_text)
        _extend_unique(skills, parsed)
        if separator and any(token in label.lower() for token in tool_labels):
            _extend_unique(tools, parsed)
    return skills, tools


def _split_list(value: str) -> List[str]:
    parts = re.split(r"[,|;\u00b7\u2022]+", value)
    return [part.strip(" -") for part in parts if part.strip(" -")]


def _parse_dated_entries(lines: List[str], entry_type: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    current: Dict[str, Any] = {}
    for line in lines:
        date_match = _entry_date_match(line, entry_type)
        if date_match:
            if current:
                entries.append(_finish_entry(current))
            title = line[:date_match.start()].strip(" \t|-")
            current = {
                "title" if entry_type != "project" else "name": title,
                "dates": date_match.group(0),
                "description_lines": [],
            }
            continue

        if not current:
            current = {
                "title" if entry_type != "project" else "name": line,
                "description_lines": [],
            }
            continue

        if entry_type == "experience" and "company" not in current:
            current["company"] = line
        elif entry_type == "project" and line.lower().startswith(("tools:", "technologies:")):
            current["technologies_used"] = line.split(":", 1)[1].strip()
        elif entry_type == "education" and "institution" not in current:
            current["institution"] = line
        else:
            current["description_lines"].append(line)

    if current:
        entries.append(_finish_entry(current))
    return [entry for entry in entries if any(entry.values())]


def _entry_date_match(line: str, entry_type: str):
    date_match = DATE_RANGE_PATTERN.search(line)
    if date_match:
        return date_match
    if entry_type == "project":
        matches = list(MONTH_YEAR_PATTERN.finditer(line))
        return matches[-1] if matches else None
    if entry_type == "education":
        matches = list(YEAR_PATTERN.finditer(line))
        return matches[-1] if matches else None
    return None


def _finish_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    description_lines = entry.pop("description_lines", [])
    if description_lines:
        entry["description"] = " ".join(description_lines)
    return entry


def _parse_certifications(lines: List[str]) -> List[Dict[str, str]]:
    certifications = []
    for line in lines:
        year_match = re.search(r"\b(19|20)\d{2}\b", line)
        certifications.append({
            "name": line.strip(),
            "year": year_match.group(0) if year_match else "",
        })
    return certifications


def _parse_languages(lines: List[str]) -> List[str]:
    for line in lines:
        match = re.search(r"languages?\s*:\s*(.+)", line, re.IGNORECASE)
        if match:
            return _split_list(match.group(1))
    return []


def _estimate_years_of_experience(
    text: str, experience: List[Dict[str, Any]]
) -> float:
    explicit = re.search(
        r"(\d+(?:\.\d+)?)\+?\s+years?(?:\s+of)?\s+(?:professional\s+)?experience",
        text,
        re.IGNORECASE,
    )
    if explicit:
        return float(explicit.group(1))

    total_months = 0
    for entry in experience:
        dates = entry.get("dates", "")
        match = DATE_RANGE_PATTERN.search(dates)
        if not match:
            continue
        start = _parse_date(match.group("start"), end=False)
        end = _parse_date(match.group("end"), end=True)
        if start and end and end >= start:
            total_months += (end.year - start.year) * 12 + end.month - start.month + 1
    return round(total_months / 12, 1) if total_months else 0.0


def _parse_date(value: str, end: bool) -> Optional[datetime]:
    if value.lower() in ("present", "current"):
        return datetime.utcnow()
    year_match = re.search(r"\b\d{4}\b", value)
    if not year_match:
        return None
    year = int(year_match.group(0))
    month = 12 if end else 1
    for token, number in MONTHS.items():
        if value.lower().startswith(token):
            month = number
            break
    return datetime(year, month, 1)


def _infer_career_level(text: str, experience: List[Dict[str, Any]]) -> str:
    lowered = text.lower()
    if "fresher" in lowered or "entry level" in lowered or "entry-level" in lowered:
        return "Entry Level"
    years = _estimate_years_of_experience(text, experience)
    if years >= 8:
        return "Senior"
    if years >= 3:
        return "Mid Level"
    return "Entry Level"


def _extend_unique(target: List[str], values: List[str]) -> None:
    existing = {value.lower() for value in target}
    for value in values:
        if value.lower() not in existing:
            target.append(value)
            existing.add(value.lower())

import logging
import re
from collections import Counter
from typing import Any, Dict, Iterable

logger = logging.getLogger("app.services.ats_scoring")

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "our",
    "that",
    "the",
    "this",
    "to",
    "with",
    "you",
    "your",
}

CATEGORY_WEIGHTS = {
    "skills": 0.20,
    "required_keywords": 0.20,
    "preferred_keywords": 0.10,
    "technologies": 0.15,
    "experience": 0.15,
    "education": 0.07,
    "certifications": 0.05,
    "title_relevance": 0.05,
    "keyword_density": 0.03,
    "section_completeness": 0.03,
    "formatting_completeness": 0.02,
}

TECH_KEYWORDS = {
    "ai",
    "airflow",
    "analytics",
    "api",
    "aws",
    "azure",
    "bigquery",
    "cloud",
    "docker",
    "excel",
    "fastapi",
    "gcp",
    "git",
    "java",
    "javascript",
    "kubernetes",
    "linux",
    "machine learning",
    "ml",
    "mongodb",
    "mysql",
    "n8n",
    "nlp",
    "pandas",
    "postgresql",
    "power bi",
    "python",
    "react",
    "sql",
    "tableau",
    "tensorflow",
    "typescript",
}

EDUCATION_TERMS = {
    "bachelor",
    "b.e",
    "btech",
    "b.tech",
    "computer science",
    "degree",
    "engineering",
    "master",
    "mba",
    "mca",
}

CERTIFICATION_TERMS = {
    "certification",
    "certified",
    "certificate",
    "aws certified",
    "azure certified",
    "google certified",
}


def _as_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return {}


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_stringify(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_stringify(item) for item in value)
    return str(value)


def _tokens(text: str) -> list[str]:
    return [
        token.lower()
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9+#.\-/]{1,}", text or "")
        if token.lower() not in STOP_WORDS and len(token) > 1
    ]


def _phrases(text: str) -> set[str]:
    normalized = re.sub(r"[^a-zA-Z0-9+#.\-/ ]+", " ", (text or "").lower())
    words = [word for word in normalized.split() if word not in STOP_WORDS]
    phrases = set(words)
    phrases.update(" ".join(words[index:index + 2]) for index in range(max(0, len(words) - 1)))
    phrases.update(" ".join(words[index:index + 3]) for index in range(max(0, len(words) - 2)))
    return {phrase.strip() for phrase in phrases if phrase.strip()}


def _normalize_terms(values: Iterable[Any]) -> list[str]:
    seen = set()
    terms = []
    for value in values:
        text = str(value).strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            terms.append(text)
    return terms


def _extract_resume_terms(resume_json: Dict[str, Any]) -> Dict[str, list[str]]:
    technical = _as_dict(resume_json.get("technical_skills"))
    parsed_skills = resume_json.get("skills") or resume_json.get("tools") or []
    terms = {
        "skills": [],
        "technologies": [],
        "education": [],
        "certifications": [],
        "titles": [],
    }

    for key in ("languages", "frameworks", "ai_ml", "automation", "cloud", "tools", "databases"):
        values = technical.get(key, [])
        terms["skills"].extend(values if isinstance(values, list) else [values])
        if key != "languages":
            terms["technologies"].extend(values if isinstance(values, list) else [values])

    if isinstance(parsed_skills, list):
        terms["skills"].extend(parsed_skills)

    for project in resume_json.get("projects", []) or []:
        project_data = _as_dict(project)
        terms["technologies"].extend(project_data.get("technologies") or [])

    for item in resume_json.get("education", []) or []:
        education = _as_dict(item)
        terms["education"].extend(
            [
                education.get("degree", ""),
                education.get("field_of_study", ""),
                education.get("institution", ""),
            ]
        )

    for item in resume_json.get("certifications", []) or []:
        certification = _as_dict(item)
        terms["certifications"].extend([certification.get("name", ""), certification.get("issuer", "")])

    for item in resume_json.get("experience", []) or []:
        experience = _as_dict(item)
        terms["titles"].append(experience.get("title", ""))

    terms["titles"].append(resume_json.get("headline", ""))
    return {key: _normalize_terms(values) for key, values in terms.items()}


def _extract_job_terms(job_description: str) -> Dict[str, list[str]]:
    text = job_description or ""
    phrase_set = _phrases(text)
    token_counts = Counter(_tokens(text))
    frequent_keywords = [
        token
        for token, _ in token_counts.most_common(30)
        if len(token) > 2
    ]
    tech_terms = [term for term in TECH_KEYWORDS if term in phrase_set or term in text.lower()]
    education_terms = [term for term in EDUCATION_TERMS if term in phrase_set or term in text.lower()]
    certification_terms = [term for term in CERTIFICATION_TERMS if term in phrase_set or term in text.lower()]
    years_match = re.search(r"(\d+)\+?\s*(?:years|yrs)", text.lower())

    return {
        "keywords": _normalize_terms([*tech_terms, *frequent_keywords]),
        "required_keywords": _normalize_terms([*tech_terms, *frequent_keywords[:12]]),
        "preferred_keywords": _normalize_terms(frequent_keywords[12:30]),
        "technologies": _normalize_terms(tech_terms),
        "education": _normalize_terms(education_terms),
        "certifications": _normalize_terms(certification_terms),
        "years_required": [years_match.group(1)] if years_match else [],
    }


def _match_terms(candidate_terms: list[str], required_terms: list[str]) -> tuple[list[str], list[str], float]:
    if not required_terms:
        return [], [], 100.0
    candidate_text = " ".join(candidate_terms).lower()
    matched = []
    missing = []
    for term in required_terms:
        normalized = term.lower()
        if normalized in candidate_text or any(normalized in candidate.lower() for candidate in candidate_terms):
            matched.append(term)
        else:
            missing.append(term)
    score = (len(matched) / len(required_terms)) * 100 if required_terms else 100.0
    return matched, missing, round(score, 2)


def _extract_years(text: str) -> float:
    values = [float(value) for value in re.findall(r"(\d+(?:\.\d+)?)\+?\s*(?:years|yrs)", text.lower())]
    return max(values) if values else 0.0


def _numeric_years(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return _extract_years(str(value))


def _score_experience(resume_json: Dict[str, Any], job_terms: Dict[str, list[str]]) -> float:
    required = float(job_terms["years_required"][0]) if job_terms["years_required"] else 0.0
    candidate_years = (
        _numeric_years(resume_json.get("years_of_experience") or resume_json.get("years_experience"))
        or _extract_years(_stringify(resume_json.get("experience")))
        or _extract_years(_stringify(resume_json))
    )
    if required <= 0:
        return 100.0 if candidate_years or resume_json.get("experience") else 65.0
    return round(min(100.0, (candidate_years / required) * 100), 2)


def _score_section_completeness(resume_json: Dict[str, Any]) -> float:
    sections = [
        resume_json.get("summary"),
        resume_json.get("education"),
        resume_json.get("experience"),
        resume_json.get("projects"),
        resume_json.get("certifications"),
        resume_json.get("technical_skills") or resume_json.get("skills"),
    ]
    present = sum(1 for section in sections if section)
    return round((present / len(sections)) * 100, 2)


def _score_formatting_completeness(resume_json: Dict[str, Any]) -> float:
    score = 0
    if resume_json.get("name"):
        score += 20
    if resume_json.get("summary"):
        score += 20
    if resume_json.get("experience"):
        score += 20
    if resume_json.get("education"):
        score += 15
    if resume_json.get("technical_skills") or resume_json.get("skills"):
        score += 15
    if resume_json.get("projects") or resume_json.get("certifications"):
        score += 10
    return float(min(100, score))


def _score_keyword_density(resume_text: str, job_keywords: list[str]) -> float:
    if not job_keywords:
        return 100.0
    text = resume_text.lower()
    hits = sum(1 for keyword in job_keywords if keyword.lower() in text)
    return round(min(100.0, (hits / max(1, min(len(job_keywords), 20))) * 100), 2)


def _score_title_relevance(resume_terms: Dict[str, list[str]], job_description: str) -> float:
    titles = resume_terms.get("titles", [])
    if not titles:
        return 50.0
    job_phrases = _phrases(job_description)
    title_tokens = set(_tokens(" ".join(titles)))
    if not title_tokens:
        return 50.0
    overlap = title_tokens.intersection(job_phrases)
    return round(min(100.0, (len(overlap) / max(1, len(title_tokens))) * 100), 2)


def calculate_ats_score(resume_json: Any, job_description: str) -> Dict[str, Any]:
    resume = _as_dict(resume_json)
    resume_text = _stringify(resume)
    job_text = job_description or ""
    resume_terms = _extract_resume_terms(resume)
    job_terms = _extract_job_terms(job_text)

    matched_skills, missing_skills, skills_score = _match_terms(
        resume_terms["skills"],
        job_terms["keywords"],
    )
    matched_required, missing_required, required_score = _match_terms(
        resume_terms["skills"],
        job_terms["required_keywords"],
    )
    matched_preferred, missing_preferred, preferred_score = _match_terms(
        resume_terms["skills"],
        job_terms["preferred_keywords"],
    )
    matched_tools, missing_tools, technology_score = _match_terms(
        resume_terms["technologies"],
        job_terms["technologies"],
    )
    _, _, education_score = _match_terms(resume_terms["education"], job_terms["education"])
    _, _, certification_score = _match_terms(
        resume_terms["certifications"],
        job_terms["certifications"],
    )

    breakdown = {
        "skills": skills_score,
        "required_keywords": required_score,
        "preferred_keywords": preferred_score,
        "technologies": technology_score,
        "experience": _score_experience(resume, job_terms),
        "education": education_score,
        "certifications": certification_score,
        "title_relevance": _score_title_relevance(resume_terms, job_text),
        "keyword_density": _score_keyword_density(resume_text, job_terms["keywords"]),
        "section_completeness": _score_section_completeness(resume),
        "formatting_completeness": _score_formatting_completeness(resume),
    }
    score = round(
        sum(breakdown[key] * weight for key, weight in CATEGORY_WEIGHTS.items()),
        2,
    )
    missing_keywords = _normalize_terms([*missing_skills, *missing_required, *missing_preferred, *missing_tools])
    matched_keywords = _normalize_terms([*matched_skills, *matched_required, *matched_preferred, *matched_tools])
    recommendations = [
        f"Add stronger evidence for {keyword}." for keyword in missing_keywords[:5]
    ]
    if breakdown["section_completeness"] < 80:
        recommendations.append("Complete missing resume sections for better ATS parsing.")

    return {
        "score": max(0, min(100, round(score))),
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "strengths": matched_keywords[:8],
        "recommendations": recommendations,
        "breakdown": breakdown,
    }

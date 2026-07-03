import re
from collections import Counter
from typing import Any, Dict, List


TECH_TERMS = {
    "python", "sql", "java", "javascript", "typescript", "react", "next.js",
    "fastapi", "django", "flask", "node.js", "postgresql", "mysql", "mongodb",
    "power bi", "tableau", "excel", "aws", "azure", "gcp", "docker",
    "kubernetes", "airflow", "spark", "snowflake", "databricks", "pandas",
    "numpy", "scikit-learn", "tensorflow", "pytorch", "machine learning",
    "artificial intelligence", "nlp", "llm", "rag", "n8n", "api", "rest",
}

SOFT_SKILLS = {
    "communication", "collaboration", "leadership", "stakeholder management",
    "problem solving", "analytical", "ownership", "teamwork", "presentation",
}

INDUSTRY_TERMS = {
    "fintech", "healthcare", "retail", "ecommerce", "e-commerce", "banking",
    "insurance", "saas", "cybersecurity", "analytics", "consulting",
}

SECTION_PATTERNS = {
    "required_skills": r"(?:required skills?|requirements?|must have|required qualifications?)[:\n](.*?)(?:preferred|responsibilities|about|qualifications|$)",
    "preferred_skills": r"(?:preferred skills?|good to have|nice to have|preferred qualifications?)[:\n](.*?)(?:responsibilities|requirements|about|$)",
    "responsibilities": r"(?:responsibilities|what you'?ll do|role and responsibilities)[:\n](.*?)(?:requirements|preferred|qualifications|about|$)",
}


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def _sentences(text: str) -> List[str]:
    return [_clean(item) for item in re.split(r"[\n.;•]+", text or "") if _clean(item)]


def _extract_section(text: str, name: str) -> List[str]:
    pattern = SECTION_PATTERNS[name]
    match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return []
    return _sentences(match.group(1))[:12]


def _phrases(text: str) -> set[str]:
    normalized = re.sub(r"[^a-z0-9+#.\-/ ]+", " ", (text or "").lower())
    words = [word for word in normalized.split() if len(word) > 1]
    phrases = set(words)
    phrases.update(" ".join(words[i:i + 2]) for i in range(max(0, len(words) - 1)))
    phrases.update(" ".join(words[i:i + 3]) for i in range(max(0, len(words) - 2)))
    return phrases


def _keywords(text: str) -> List[str]:
    tokens = [
        token.lower()
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9+#.\-/]{2,}", text or "")
        if token.lower() not in {"and", "the", "for", "with", "you", "our", "will", "are", "this", "that"}
    ]
    return [token for token, _ in Counter(tokens).most_common(30)]


def analyze_job_description(job: Any) -> Dict[str, Any]:
    description = getattr(job, "description", None) or ""
    title = getattr(job, "title", None) or ""
    text = f"{title}\n{description}"
    phrase_set = _phrases(text)
    lower_text = text.lower()
    years_match = re.search(r"(\d+)\+?\s*(?:years|yrs)", lower_text)

    required_technologies = sorted(term for term in TECH_TERMS if term in phrase_set or term in lower_text)
    soft_skills = sorted(term for term in SOFT_SKILLS if term in phrase_set or term in lower_text)
    industries = sorted(term for term in INDUSTRY_TERMS if term in phrase_set or term in lower_text)

    role = title
    if not role:
        role_match = re.search(r"(?:role|position)[:\s]+([a-zA-Z0-9 /+-]+)", description, re.IGNORECASE)
        role = _clean(role_match.group(1)) if role_match else ""

    required_skills = _extract_section(description, "required_skills")
    preferred_skills = _extract_section(description, "preferred_skills")
    responsibilities = _extract_section(description, "responsibilities")

    return {
        "role": role,
        "industry": industries[0] if industries else "",
        "experience_level": f"{years_match.group(1)}+ years" if years_match else "",
        "required_skills": required_skills or required_technologies[:12],
        "preferred_skills": preferred_skills,
        "responsibilities": responsibilities,
        "required_technologies": required_technologies,
        "soft_skills": soft_skills,
        "keywords": _keywords(text),
        "tailoring_guardrails": [
            "Preserve 90-95% of the original resume facts.",
            "Tailor only summary, headline, skills ordering, project ordering, and experience bullet wording.",
            "Never modify dates, companies, education, certifications, project facts, achievements, or metrics.",
            "Keep ATS layout identical and optimize keyword coverage without exaggeration.",
        ],
    }

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from app.models.resume_schema import ResumeSchema
from app.services.resume_generation_config import ACTION_VERBS


SENIORITY_TERMS = re.compile(r"\b(senior|sr\.?|lead|principal|staff|manager|head)\b", re.IGNORECASE)
VERB_HINTS = {
    "is",
    "are",
    "was",
    "were",
    "be",
    "being",
    "been",
    "build",
    "built",
    "analyze",
    "analyzed",
    "analysed",
    "develop",
    "developed",
    "design",
    "designed",
    "deliver",
    "delivered",
    "implement",
    "implemented",
    "optimize",
    "optimized",
    "automate",
    "automated",
    "identify",
    "identified",
    "reduce",
    "reduced",
    "create",
    "created",
    "generate",
    "generated",
}


@dataclass
class ResumeValidationResult:
    valid: bool
    violations: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    word_count: int = 0
    manual_review_required: bool = False


def normalize_tokens(value: Any) -> list[str]:
    return re.sub(r"[^a-z0-9+#.\-/ ]+", " ", str(value or "").lower()).split()


def first_words(value: str, count: int = 4) -> list[str]:
    return normalize_tokens(value)[:count]


def bullet_openings_overlap(left: str, right: str) -> bool:
    left_words = first_words(left, 6)
    right_words = first_words(right, 6)
    if len(left_words) < 4 or len(right_words) < 4:
        return False
    return len(set(left_words[:6]) & set(right_words[:6])) >= 4


def sentence_has_verb(sentence: str) -> bool:
    tokens = set(normalize_tokens(sentence))
    if tokens & VERB_HINTS:
        return True
    return any(token.endswith("ed") or token.endswith("ing") for token in tokens)


def approved_action_verb(bullet: str) -> bool:
    first = first_words(bullet, 1)
    if not first:
        return False
    return first[0] in {verb.lower() for verb in ACTION_VERBS}


def parse_month_year(value: str) -> Optional[datetime]:
    value = str(value or "").strip()
    if not value or value.lower() in {"present", "current", "now"}:
        return datetime.utcnow()
    for fmt in ("%b %Y", "%B %Y", "%m/%Y", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    year_match = re.search(r"\b(20\d{2}|19\d{2})\b", value)
    if year_match:
        return datetime(int(year_match.group(1)), 1, 1)
    return None


def compute_total_experience_months(resume: ResumeSchema, candidate_profile: Optional[Dict[str, Any]] = None) -> int:
    explicit = (candidate_profile or {}).get("years_of_experience") or (candidate_profile or {}).get("years_experience")
    if explicit not in (None, ""):
        match = re.search(r"\d+(?:\.\d+)?", str(explicit))
        if match:
            return int(float(match.group(0)) * 12)

    total = 0
    for entry in resume.experience:
        start = parse_month_year(entry.start_date)
        end = parse_month_year(entry.end_date)
        if start and end and end >= start:
            total += max(1, (end.year - start.year) * 12 + (end.month - start.month))
    return total


def resume_word_count(resume: ResumeSchema) -> int:
    text = json.dumps(resume.model_dump(), default=str)
    return len(re.findall(r"\b[\w+#.\-/]+\b", text))


def collect_missing_fields(resume: ResumeSchema) -> list[str]:
    missing = []
    contact = resume.contact
    for key in ("email", "phone", "location", "linkedin", "github"):
        if not getattr(contact, key, ""):
            missing.append(f"contact.{key}")
    for index, edu in enumerate(resume.education):
        if not edu.degree:
            missing.append(f"education[{index}].degree")
        if not edu.institution:
            missing.append(f"education[{index}].institution")
        if not (edu.graduation_date or edu.end_date):
            missing.append(f"education[{index}].grad_date")
        details_text = " ".join(edu.details)
        if not re.search(r"\b(CGPA|GPA|percentage|%)\b", details_text, re.IGNORECASE):
            missing.append(f"education[{index}].score")
    return missing


def validate_bullet_list(path: str, bullets: Iterable[str], violations: list[str]) -> None:
    previous = ""
    used_verbs: set[str] = set()
    for index, bullet in enumerate(bullets or []):
        text = str(bullet or "").strip()
        if not text:
            continue
        if previous and bullet_openings_overlap(previous, text):
            violations.append(f"{path}.bullets[{index}] repeats the opening of the previous bullet.")
        if not approved_action_verb(text):
            violations.append(f"{path}.bullets[{index}] must start with an approved action verb.")
        first = first_words(text, 1)
        if first:
            if first[0] in used_verbs:
                violations.append(f"{path}.bullets[{index}] reuses action verb '{first[0]}'.")
            used_verbs.add(first[0])
        previous = text


def validate_resume_json(
    resume: ResumeSchema,
    *,
    candidate_profile: Optional[Dict[str, Any]] = None,
    min_words: int = 475,
    max_words: int = 600,
) -> ResumeValidationResult:
    violations: list[str] = []
    summary_sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", resume.summary or "")
        if sentence.strip()
    ]
    if not 2 <= len(summary_sentences) <= 3:
        violations.append("summary must contain 2-3 complete sentences.")
    for index, sentence in enumerate(summary_sentences):
        if len(sentence.split()) > 40:
            violations.append(f"summary sentence {index + 1} exceeds 40 words.")
        if not sentence_has_verb(sentence):
            violations.append(f"summary sentence {index + 1} appears to be a fragment.")
        if "Selected impact:" in sentence:
            violations.append("summary contains dangling label 'Selected impact:'.")

    total_months = compute_total_experience_months(resume, candidate_profile)
    if total_months < 24 and SENIORITY_TERMS.search(" ".join([resume.headline, *[entry.title for entry in resume.experience]])):
        violations.append("seniority-inflating title appears with computed experience under 24 months.")

    for index, entry in enumerate(resume.experience):
        if len(entry.bullets) < 2:
            violations.append(f"experience[{index}] must contain at least 2 bullets when source data supports it.")
        if len(entry.bullets) > 4:
            violations.append(f"experience[{index}] must contain no more than 4 bullets.")
        validate_bullet_list(f"experience[{index}]", entry.bullets, violations)

    for index, entry in enumerate(resume.projects):
        if len(entry.bullets) > 4:
            violations.append(f"projects[{index}] must contain no more than 4 bullets.")
        validate_bullet_list(f"projects[{index}]", entry.bullets, violations)

    words = resume_word_count(resume)
    if words < min_words:
        violations.append(f"resume body is under target length ({words} words); expand experience/projects with supported facts.")
    elif words > max_words:
        violations.append(f"resume body exceeds target length ({words} words); trim summary/projects/certifications.")

    missing_fields = collect_missing_fields(resume)
    return ResumeValidationResult(
        valid=not violations,
        violations=violations,
        missing_fields=missing_fields,
        word_count=words,
    )

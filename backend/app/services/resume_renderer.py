from pathlib import Path
import logging
import re
from typing import Any, Iterable, Mapping, Union

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.models.resume_schema import ResumeSchema
from app.services.resume_generation_config import ACTION_VERBS
from app.services.resume_generation_config import SECTION_LABELS


APP_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = APP_ROOT / "templates"
STYLESHEET_PATH = APP_ROOT / "static" / "css" / "resume.css"
logger = logging.getLogger("app.services.resume_renderer")

template_environment = Environment(
    loader=FileSystemLoader(str(TEMPLATE_ROOT)),
    autoescape=select_autoescape(("html", "xml")),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


def format_resume_date(value: Any) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    if text.lower() in {"present", "current", "now"}:
        return "Present"
    match = re.search(r"\b(20\d{2}|19\d{2})\b", text)
    if re.fullmatch(r"\d{4}", text):
        return text
    for pattern, replacement in (
        (r"^(\d{4})-(\d{1,2})$", None),
        (r"^(\d{1,2})/(\d{4})$", None),
    ):
        matched = re.match(pattern, text)
        if matched:
            if pattern.startswith("^(\\d{4})"):
                year, month = matched.groups()
            else:
                month, year = matched.groups()
            month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            month_index = max(1, min(12, int(month))) - 1
            return f"{month_names[month_index]} {year}"
    return text if not match else text


template_environment.filters["resume_date"] = format_resume_date


SKILL_GROUPS = {
    "languages": {
        "c",
        "c++",
        "c#",
        "go",
        "golang",
        "java",
        "javascript",
        "kotlin",
        "php",
        "python",
        "r",
        "ruby",
        "rust",
        "scala",
        "sql",
        "swift",
        "typescript",
    },
    "frameworks": {
        "angular",
        "django",
        "express",
        "fastapi",
        "flask",
        "flutter",
        "laravel",
        "next.js",
        "nextjs",
        "node.js",
        "nodejs",
        "react",
        "spring",
        "vue",
    },
    "ai_ml": {
        "ai",
        "ann",
        "artificial intelligence",
        "bert",
        "computer vision",
        "cuda",
        "deep learning",
        "gemini",
        "groq",
        "hugging face",
        "langchain",
        "llm",
        "machine learning",
        "ml",
        "nlp",
        "openai",
        "opencv",
        "pandas",
        "pytorch",
        "rag",
        "scikit-learn",
        "sklearn",
        "tensorflow",
        "transformers",
        "yolo",
    },
    "automation": {
        "airflow",
        "automation",
        "ci/cd",
        "github actions",
        "n8n",
        "power automate",
        "selenium",
        "zapier",
    },
    "bi_analytics": {
        "analytics",
        "bigquery",
        "business intelligence",
        "dax",
        "excel",
        "looker",
        "looker studio",
        "power bi",
        "reporting",
        "tableau",
        "visualization",
    },
    "tools": {
        "bitbucket",
        "docker",
        "git",
        "github",
        "gitlab",
        "jira",
        "linux",
        "postman",
        "power bi",
        "tableau",
        "vscode",
        "vs code",
    },
    "platforms": {
        "android",
        "aws",
        "azure",
        "gcp",
        "google cloud",
        "heroku",
        "kubernetes",
        "linux",
        "salesforce",
        "windows",
    },
    "databases": {
        "bigquery",
        "dynamodb",
        "elasticsearch",
        "mongodb",
        "ms sql",
        "mysql",
        "oracle",
        "postgres",
        "postgresql",
        "redis",
        "snowflake",
        "sqlite",
    },
    "cloud": {
        "aws",
        "azure",
        "cloud",
        "docker",
        "gcp",
        "google cloud",
        "kubernetes",
        "lambda",
    },
}


def _dedupe(items: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


TECH_CANONICAL_NAMES = {
    "power bi": "Power BI",
    "python": "Python",
    "sql": "SQL",
    "tableau": "Tableau",
    "excel": "Excel",
    "looker": "Looker",
    "looker studio": "Looker Studio",
    "bigquery": "BigQuery",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "mongodb": "MongoDB",
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "react": "React",
    "aws": "AWS",
    "azure": "Azure",
    "gcp": "GCP",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "scikit-learn": "Scikit-learn",
    "sklearn": "Scikit-learn",
    "tensorflow": "TensorFlow",
    "pytorch": "PyTorch",
    "airflow": "Airflow",
    "n8n": "n8n",
}


def canonical_technology(value: Any) -> str:
    text = " ".join(str(value or "").replace(".", ".").split()).strip(" |.,")
    normalized = _normalize_text(text)
    return TECH_CANONICAL_NAMES.get(normalized, text[:1].upper() + text[1:] if text else "")


def _normalize_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9+#.\-/ ]+", " ", str(value or "").lower()).strip()


def _content_quality(text: str) -> tuple[int, int]:
    metric_score = 1 if re.search(r"\d+%|\d+\+?|\b(reduced|improved|automated|optimized|increased|decreased|delivered|built|designed)\b", text, re.I) else 0
    return metric_score, len(str(text or ""))


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
    normalized = _normalize_text(text)
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


def _is_near_duplicate(left: str, right: str) -> bool:
    left_key = _normalize_text(left)
    right_key = _normalize_text(right)
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


def _dedupe_quality(items: Iterable[Any]) -> list[str]:
    selected: list[str] = []
    for item in items or []:
        text = " ".join(str(item or "").split())
        key = _normalize_text(text)
        if not key:
            continue
        duplicate_index = next(
            (index for index, existing in enumerate(selected) if _is_near_duplicate(text, existing)),
            None,
        )
        if duplicate_index is None:
            selected.append(text)
            continue
        if _content_quality(text) > _content_quality(selected[duplicate_index]):
            selected[duplicate_index] = text
    return selected


def _dedupe_entries(items: Iterable[Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        identity = " ".join(_normalize_text(item.get(key, "")) for key in keys if item.get(key)).strip()
        if not identity:
            identity = _normalize_text(json_dump_resume(item))
        if identity in seen:
            continue
        seen.add(identity)
        selected.append(item)
    return selected


def _dedupe_sentence_text(text: str) -> str:
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", str(text or ""))
        if sentence.strip()
    ]
    if len(sentences) <= 1:
        return " ".join(str(text or "").split())
    return " ".join(_dedupe_quality(sentences))


def _clean_resume_copy(text: Any) -> str:
    value = " ".join(str(text or "").split())
    value = re.sub(r"\b(\d+(?:\.\d+)?)\s+of experience\b", r"\1 years of experience", value, flags=re.IGNORECASE)
    value = re.sub(r"\bSelected impact:\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\bKnown for analysed\b", "Analysed", value, flags=re.IGNORECASE)
    value = re.sub(r"\bKnown for analyzed\b", "Analyzed", value, flags=re.IGNORECASE)
    value = re.sub(r"\bKnown for built\b", "Built", value, flags=re.IGNORECASE)
    value = re.sub(r"\bKnown for designed\b", "Designed", value, flags=re.IGNORECASE)
    return value


def collapse_action_verb_collision(text: Any) -> str:
    value = re.sub(r"\b(\w+)\s+\1\b", r"\1", str(text or ""), flags=re.IGNORECASE)
    approved = "|".join(sorted((re.escape(str(verb).lower()) for verb in ACTION_VERBS), key=len, reverse=True))
    weak = r"wrote|conducted|created|made|did|worked|handled|helped|used|analysed"
    if approved:
        value = re.sub(
            rf"^({approved})\s+({approved}|{weak})\b\s*",
            lambda match: f"{match.group(1)} ",
            value,
            flags=re.IGNORECASE,
        )
    value = value.strip(" ;,.")
    if value:
        value = f"{value[0].upper()}{value[1:]}"
        if value[-1] not in ".!?":
            value = f"{value}."
    return value


def _leading_signature(text: str) -> str:
    normalized = _normalize_text(text)
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
        text = collapse_action_verb_collision(_clean_resume_copy(bullet))
        signature = _leading_signature(text)
        if signature and signature in signatures:
            parts = [part.strip() for part in re.split(r"\s*;\s*", text, maxsplit=1) if part.strip()]
            if len(parts) == 2 and len(parts[1].split()) >= 6:
                text = _capitalize_sentence(parts[1])
            else:
                comma_parts = [part.strip() for part in re.split(r"\s*,\s*", text, maxsplit=1) if part.strip()]
                if len(comma_parts) == 2 and len(comma_parts[1].split()) >= 6:
                    text = _capitalize_sentence(comma_parts[1])
        signature = _leading_signature(text)
        if signature:
            signatures.add(signature)
        cleaned.append(text)
    return cleaned


def _is_skill_like(value: Any) -> bool:
    text = " ".join(str(value or "").split())
    normalized = _normalize_text(text)
    if not normalized:
        return False
    banned_phrases = {
        "business impact",
        "measurable business impact",
        "hands on experience",
        "production ready outcomes",
        "stakeholder requirements",
        "clear impact",
    }
    if normalized in banned_phrases:
        return False
    if len(text) > 42 and not any(char in text for char in ("/", "+", "#", ".")):
        return False
    if len(normalized.split()) > 5:
        return False
    return True


def _dedupe_skills(items: Iterable[Any]) -> list[str]:
    return _dedupe_quality(item for item in items or [] if _is_skill_like(item))


def _cap_bullets(items: Iterable[Any], limit: int) -> list[str]:
    bullets = _dedupe_quality(collapse_action_verb_collision(item) for item in items or [])
    ranked = sorted(
        enumerate(bullets),
        key=lambda pair: (_content_quality(pair[1]), -pair[0]),
        reverse=True,
    )
    selected_indexes = sorted(index for index, _ in ranked[:limit])
    return _remove_repeated_bullet_openers([bullets[index] for index in selected_indexes])


def _technical_skill_values(skills: Any, key: str) -> list[str]:
    value = getattr(skills, key, None)
    if value is None and getattr(skills, "model_extra", None):
        value = skills.model_extra.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return _dedupe_skills(value)
    return [str(value).strip()] if str(value).strip() else []


def _matches_skill_group(skill: str, group_terms: set[str]) -> bool:
    normalized = skill.lower().strip()
    return any(term == normalized or term in normalized for term in group_terms)


def build_skill_groups(resume: ResumeSchema) -> list[dict[str, Any]]:
    skills = resume.technical_skills
    groups = {
        "Programming Languages": _technical_skill_values(skills, "languages"),
        "Databases": _technical_skill_values(skills, "databases"),
        "BI / Analytics": [],
        "AI / ML": _technical_skill_values(skills, "ai_ml"),
        "Cloud": _technical_skill_values(skills, "cloud"),
        "Developer Tools": _technical_skill_values(skills, "automation"),
        "Platforms": [],
    }
    framework_values = _technical_skill_values(skills, "frameworks")
    groups["Developer Tools"].extend(framework_values)

    assigned = {
        _normalize_text(item)
        for values in groups.values()
        for item in values
    }
    ungrouped = [
        item
        for item in _technical_skill_values(skills, "tools")
        if _normalize_text(item) not in assigned
    ]

    for skill in ungrouped:
        for group_key, terms in SKILL_GROUPS.items():
            label = {
                "languages": "Programming Languages",
                "frameworks": "Developer Tools",
                "ai_ml": "AI / ML",
                "automation": "Developer Tools",
                "databases": "Databases",
                "cloud": "Cloud",
                "bi_analytics": "BI / Analytics",
                "tools": "Developer Tools",
                "platforms": "Platforms",
            }.get(group_key)
            normalized_skill = _normalize_text(skill)
            if label and _matches_skill_group(skill, terms):
                if normalized_skill in assigned:
                    break
                groups[label].append(skill)
                assigned.add(normalized_skill)
                break
        else:
            normalized_skill = _normalize_text(skill)
            if normalized_skill not in assigned:
                groups["Developer Tools"].append(skill)
                assigned.add(normalized_skill)

    return [
        {"label": label, "items": _dedupe_skills(values)}
        for label, values in groups.items()
        if _dedupe_skills(values)
    ]


def build_language_list(resume: ResumeSchema) -> list[str]:
    extras = getattr(resume, "model_extra", None) or {}
    value = extras.get("languages") or extras.get("spoken_languages") or []
    if isinstance(value, str):
        value = [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return _dedupe(value)
    return []


def clean_headline(value: Any) -> str:
    parts = [
        part.strip()
        for part in re.split(r"\s*\|\s*|,", str(value or ""))
        if part.strip()
    ]
    if not parts:
        return ""
    role = parts[0].strip(" |.,")
    if role.islower() or role.isupper():
        role = role.title()
    technologies = _dedupe(
        canonical_technology(part)
        for part in parts[1:]
        if canonical_technology(part)
    )[:5]
    headline = f"{role} | {' | '.join(technologies)}" if technologies else role
    return headline[:90].rstrip(" |,.")


def clean_certification_text(value: Any) -> str:
    text = " ".join(str(value or "").split())
    while re.search(r"\((\d{4})\)\s*\(\1\)", text):
        text = re.sub(r"\((\d{4})\)\s*\(\1\)", r"(\1)", text)
    text = re.sub(r"\b(20\d{2}|19\d{2})\s+\1\b", r"\1", text)
    return text


def certification_identity(value: Any) -> str:
    text = clean_certification_text(value)
    text = re.sub(r"\(?\b(20\d{2}|19\d{2})\b\)?", "", text)
    text = re.sub(r"[\s\-–—_]+", "", text)
    return re.sub(r"[^a-z0-9+#.]+", "", text.lower())


def extract_certification_year(*values: Any) -> str:
    for value in values:
        match = re.search(r"\b(20\d{2}|19\d{2})\b", str(value or ""))
        if match:
            return match.group(1)
    return ""


def dedupe_certifications(entries: Iterable[Any]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries or []:
        cleaned = dict(entry) if isinstance(entry, dict) else {"name": str(entry or "").strip()}
        cleaned["name"] = clean_certification_text(cleaned.get("name", ""))
        cleaned["issuer"] = clean_certification_text(cleaned.get("issuer", ""))
        year = extract_certification_year(cleaned.get("date"), cleaned.get("name"), cleaned.get("issuer"))
        cleaned["name"] = re.sub(r"\s*\(?\b(20\d{2}|19\d{2})\b\)?", "", cleaned["name"]).strip(" -–—,")
        cleaned["issuer"] = re.sub(r"\s*\(?\b(20\d{2}|19\d{2})\b\)?", "", cleaned["issuer"]).strip(" -–—,")
        cleaned["date"] = year
        key = certification_identity(cleaned.get("name", ""))
        if not key:
            continue
        duplicate = any(
            key == existing
            or (len(key) >= 12 and key in existing)
            or (len(existing) >= 12 and existing in key)
            for existing in seen
        )
        if duplicate:
            continue
        seen.add(key)
        selected.append(cleaned)
    return selected


def estimate_resume_density(resume: ResumeSchema) -> str:
    data = resume.model_dump()
    bullet_count = sum(len(entry.get("bullets") or []) for section in ("experience", "projects", "research") for entry in data.get(section, []) or [])
    entry_count = sum(len(data.get(section, []) or []) for section in ("experience", "projects", "education", "research"))
    cert_count = len(data.get("certifications", []) or [])
    skill_count = sum(len(value or []) for value in (data.get("technical_skills") or {}).values() if isinstance(value, list))
    word_count = len(re.findall(r"\b[\w+#.\-/]+\b", json_dump_resume(data)))
    score = word_count + bullet_count * 18 + entry_count * 22 + cert_count * 10 + skill_count * 2
    if score > 1220:
        return "density-tight"
    if score > 1040:
        return "density-compact"
    return "density-normal"


def json_dump_resume(data: Mapping[str, Any]) -> str:
    import json

    return json.dumps(data, default=str)


def build_display_resume(resume: ResumeSchema) -> ResumeSchema:
    data = resume.model_dump()
    if not str(data.get("name") or "").strip():
        data["name"] = "Candidate"
    data["headline"] = clean_headline(_clean_resume_copy(data.get("headline") or ""))
    data["summary"] = _dedupe_sentence_text(_clean_resume_copy(data.get("summary") or ""))

    data["experience"] = _dedupe_entries(data.get("experience", []) or [], ("company", "title", "location", "start_date", "end_date"))
    data["projects"] = _dedupe_entries(data.get("projects", []) or [], ("name", "role", "date"))

    for entry in data.get("experience", []) or []:
        entry["bullets"] = _cap_bullets(entry.get("bullets", []), 4)

    for entry in data.get("projects", []) or []:
        entry["bullets"] = _cap_bullets(entry.get("bullets", []), 4)
        entry["technologies"] = _dedupe_quality(entry.get("technologies", []))
        if entry.get("description") and not entry.get("bullets"):
            entry["bullets"] = _cap_bullets([entry["description"]], 4)
            entry["description"] = ""

    for entry in data.get("research", []) or []:
        entry["bullets"] = _cap_bullets(entry.get("bullets", []), 3)

    data["certifications"] = dedupe_certifications(data.get("certifications", []))

    technical = data.get("technical_skills") or {}
    for key, value in list(technical.items()):
        if isinstance(value, list):
            technical[key] = _dedupe_skills(value)
    data["technical_skills"] = technical
    return ResumeSchema.model_validate(data)


def render_resume(
    resume_json: Union[ResumeSchema, Mapping[str, Any]],
) -> str:
    resume = (
        resume_json
        if isinstance(resume_json, ResumeSchema)
        else ResumeSchema.model_validate(resume_json)
    )
    resume = build_display_resume(resume)
    template = template_environment.get_template("resume/ats_resume.html")
    logger.info(
        "Rendering ATS resume template: template_path=%s stylesheet_path=%s stylesheet_uri=%s",
        template.filename,
        STYLESHEET_PATH.resolve(),
        STYLESHEET_PATH.resolve().as_uri(),
    )
    return template.render(
        resume=resume,
        density_class=estimate_resume_density(resume),
        skill_groups=build_skill_groups(resume),
        language_list=build_language_list(resume),
        section_labels=SECTION_LABELS,
        missing_fields=resume.missing_fields,
        stylesheet_uri=STYLESHEET_PATH.resolve().as_uri(),
    )

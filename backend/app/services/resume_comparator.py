from typing import Any, Dict


SECTION_KEYS = [
    "summary",
    "education",
    "experience",
    "projects",
    "research",
    "certifications",
    "technical_skills",
]


def _as_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value if isinstance(value, dict) else {}


def _section_size(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return 1 if value.strip() else 0
    if isinstance(value, dict):
        return sum(_section_size(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return sum(1 for item in value if _section_size(item))
    return 1


def compare_keyword_coverage(
    before_score_result: Dict[str, Any],
    after_score_result: Dict[str, Any],
) -> Dict[str, Any]:
    before_matched = set(before_score_result.get("matched_keywords") or [])
    after_matched = set(after_score_result.get("matched_keywords") or [])
    before_missing = set(before_score_result.get("missing_keywords") or [])
    after_missing = set(after_score_result.get("missing_keywords") or [])

    added_keywords = sorted(after_matched - before_matched)
    removed_keywords = sorted(before_matched - after_matched)
    resolved_missing = sorted(before_missing - after_missing)
    new_missing = sorted(after_missing - before_missing)

    return {
        "added_keywords": added_keywords,
        "removed_keywords": removed_keywords,
        "resolved_missing_keywords": resolved_missing,
        "new_missing_keywords": new_missing,
        "matched_keywords": sorted(after_matched),
        "missing_keywords": sorted(after_missing),
    }


def compare_structure(
    original_resume_json: Any,
    tailored_resume_json: Any,
) -> Dict[str, Any]:
    original = _as_dict(original_resume_json)
    tailored = _as_dict(tailored_resume_json)
    sections_modified = []

    for section in SECTION_KEYS:
        before_size = _section_size(original.get(section))
        after_size = _section_size(tailored.get(section))
        if before_size != after_size:
            sections_modified.append(section)

    return {
        "sections_modified": sections_modified,
        "original_section_count": sum(1 for key in SECTION_KEYS if _section_size(original.get(key))),
        "tailored_section_count": sum(1 for key in SECTION_KEYS if _section_size(tailored.get(key))),
    }


def _confidence(before_score: Any, after_score: Any, sections_modified: list[str]) -> int:
    if before_score is None or after_score is None:
        return 50
    delta = abs(after_score - before_score)
    confidence = 70 + min(20, int(delta * 1.5))
    if sections_modified:
        confidence += min(5, len(sections_modified))
    return max(50, min(98, confidence))


def compare_resume_quality(
    *,
    before_score_result: Dict[str, Any],
    after_score_result: Dict[str, Any],
    original_resume_json: Any,
    tailored_resume_json: Any,
) -> Dict[str, Any]:
    before_score = before_score_result.get("score")
    after_score = after_score_result.get("score")
    improvement = (
        after_score - before_score
        if before_score is not None and after_score is not None
        else None
    )
    keyword_report = compare_keyword_coverage(before_score_result, after_score_result)
    structure_report = compare_structure(original_resume_json, tailored_resume_json)

    if improvement is None:
        resume_used = "tailored"
        recommendation = "ATS score comparison was unavailable, so the tailored resume was kept."
    elif improvement > 0:
        resume_used = "tailored"
        recommendation = f"Tailored resume improved keyword coverage by {round(improvement)}%."
    else:
        resume_used = "original"
        recommendation = "The uploaded resume is already more ATS optimized."

    return {
        "before_score": before_score,
        "after_score": after_score,
        "improvement": improvement,
        "resume_used": resume_used,
        "matched_keywords": keyword_report["matched_keywords"],
        "missing_keywords": keyword_report["missing_keywords"],
        "sections_modified": structure_report["sections_modified"],
        "recommendation": recommendation,
        "reason": recommendation,
        "confidence": _confidence(
            before_score,
            after_score,
            structure_report["sections_modified"],
        ),
        "keyword_report": keyword_report,
        "structure_report": structure_report,
    }

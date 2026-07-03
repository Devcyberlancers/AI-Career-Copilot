import hashlib
import logging
import os
import re
import threading
from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger("app.services.job_match_ai")

PRIMARY_MODEL = os.getenv("JOB_MATCH_PRIMARY_MODEL", "BAAI/bge-base-en-v1.5")
FALLBACK_MODEL = os.getenv(
    "JOB_MATCH_FALLBACK_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2",
)
SKILL_MATCH_THRESHOLD = float(os.getenv("JOB_MATCH_SKILL_THRESHOLD", "0.62"))
MAX_CACHE_ITEMS = int(os.getenv("JOB_MATCH_EMBEDDING_CACHE_SIZE", "512"))


class JobMatchAIService:
    _instance: Optional["JobMatchAIService"] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "JobMatchAIService":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._model: Optional[Any] = None
        self._model_name = ""
        self._load_attempted = False
        self._load_error = ""
        self._model_lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._embedding_cache: OrderedDict[str, Any] = OrderedDict()

    @property
    def model_name(self) -> str:
        return self._model_name

    def load_model(self) -> None:
        if self._model is not None:
            return
        if self._load_attempted and self._load_error:
            raise RuntimeError(self._load_error)
        with self._model_lock:
            if self._model is not None:
                return
            if self._load_attempted and self._load_error:
                raise RuntimeError(self._load_error)

            self._load_attempted = True
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                self._load_error = (
                    "Sentence Transformer dependencies are not installed. Run "
                    "`python -m pip install -r requirements.txt` inside backend."
                )
                raise RuntimeError(self._load_error) from exc

            errors = []
            for model_name in (PRIMARY_MODEL, FALLBACK_MODEL):
                try:
                    logger.info("Loading job match embedding model: %s", model_name)
                    self._model = SentenceTransformer(model_name)
                    self._model_name = model_name
                    logger.info("Job match embedding model ready: %s", model_name)
                    return
                except Exception as exc:
                    errors.append(f"{model_name}: {exc}")
                    logger.exception("Could not load embedding model %s", model_name)

            self._load_error = (
                "No Hugging Face job-match model could be loaded. "
                + " | ".join(errors)
            )
            raise RuntimeError(self._load_error)

    def generate_match_score(
        self,
        candidate_profile: Dict[str, Any],
        job: Any,
    ) -> Dict[str, Any]:
        self.load_model()

        candidate_text = self.build_candidate_text(candidate_profile)
        job_text = self.build_job_text(job)
        if not candidate_text:
            raise ValueError("Candidate profile does not contain scorable resume data.")
        if not job_text:
            raise ValueError("Job does not contain a title or description.")

        candidate_embedding = self._embed(candidate_text)
        job_embedding = self._embed(job_text)
        # Embeddings are normalized by SentenceTransformer, so their dot product
        # is cosine similarity without requiring sklearn during app import.
        raw_similarity = float(candidate_embedding @ job_embedding)
        semantic_score = round(max(0.0, min(1.0, raw_similarity)) * 100, 2)
        confidence = round(min(98.0, max(55.0, 60.0 + (semantic_score * 0.38))), 2)

        candidate_terms = self.extract_candidate_terms(candidate_profile)
        job_requirements = self.extract_job_requirements(
            str(getattr(job, "description", "") or "")
        )
        matched_skills, missing_skills, requirement_matches = (
            self._compare_requirements(candidate_terms, job_requirements)
        )
        recommendations = [
            f"Build evidence of {requirement} through a project, course, or work example."
            for requirement in missing_skills[:5]
        ]
        if not recommendations and matched_skills:
            recommendations.append(
                "Emphasize the matched skills in the resume summary and recent experience."
            )

        explanation = self._build_explanation(
            semantic_score,
            matched_skills,
            missing_skills,
        )

        return {
            "match_score": semantic_score,
            "semantic_score": semantic_score,
            "confidence": confidence,
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "matched_tools": [],
            "missing_tools": [],
            "experience_gap": 0.0,
            "recommendations": recommendations,
            "score_breakdown": {
                "semantic": semantic_score,
                "confidence": confidence,
                "model": self.model_name,
                "scoring_engine": "huggingface_sentence_transformer",
                "candidate_text_length": len(candidate_text),
                "job_text_length": len(job_text),
                "skill_match_threshold": SKILL_MATCH_THRESHOLD,
                "requirement_matches": requirement_matches,
                "explanations": {
                    "semantic": explanation,
                },
            },
        }

    def build_candidate_text(self, profile: Dict[str, Any]) -> str:
        sections = []
        field_labels = (
            ("summary", "Professional summary"),
            ("desired_role", "Target role"),
            ("skills", "Skills"),
            ("tools", "Tools and technologies"),
            ("technologies", "Technologies"),
            ("projects", "Projects"),
            ("experience", "Experience"),
            ("education", "Education"),
            ("certifications", "Certifications"),
            ("years_of_experience", "Years of experience"),
            ("years_experience", "Years of experience"),
        )
        for key, label in field_labels:
            values = self._flatten_strings(profile.get(key))
            if values:
                sections.append(f"{label}: {'; '.join(values)}")
        return "\n".join(sections).strip()

    def build_job_text(self, job: Any) -> str:
        title = str(getattr(job, "title", "") or "").strip()
        description = str(getattr(job, "description", "") or "").strip()
        company = str(getattr(job, "company", "") or "").strip()
        parts = [
            f"Job title: {title}" if title else "",
            f"Company: {company}" if company else "",
            f"Job description and requirements: {description}" if description else "",
        ]
        return "\n".join(part for part in parts if part).strip()

    def extract_candidate_terms(self, profile: Dict[str, Any]) -> List[str]:
        values = []
        for key in ("skills", "tools", "technologies", "certifications"):
            values.extend(self._flatten_strings(profile.get(key)))
        for project in self._as_list(profile.get("projects")):
            if isinstance(project, dict):
                values.extend(
                    self._flatten_strings(
                        project.get("technologies_used")
                        or project.get("technologies")
                        or project.get("tech_stack")
                    )
                )

        terms = []
        for value in values:
            for part in re.split(r"[,|;/\n\u00b7\u2022]+", value):
                cleaned = self._clean_phrase(part)
                if cleaned and cleaned not in terms:
                    terms.append(cleaned)
        return terms[:100]

    def extract_job_requirements(self, job_text: str) -> List[str]:
        chunks = re.split(r"[\n\r\u2022]+|(?<=[.!?])\s+|[;|]+", job_text)
        phrases = []
        for chunk in chunks:
            chunk = re.sub(
                r"^(requirements?|required skills?|qualifications?|skills?|technologies?|tools?)\s*:\s*",
                "",
                chunk.strip(),
                flags=re.IGNORECASE,
            )
            for part in re.split(r",|\s+and\s+|\s+or\s+", chunk):
                cleaned = self._clean_phrase(part)
                word_count = len(cleaned.split())
                if 1 <= word_count <= 12 and len(cleaned) <= 100 and cleaned not in phrases:
                    phrases.append(cleaned)
        return phrases[:80]

    def _compare_requirements(
        self,
        candidate_terms: List[str],
        job_requirements: List[str],
    ) -> Tuple[List[str], List[str], List[Dict[str, Any]]]:
        if not job_requirements:
            return [], [], []
        if not candidate_terms:
            return [], job_requirements[:15], []

        candidate_embeddings = self._embed_many(candidate_terms)
        requirement_embeddings = self._embed_many(job_requirements)
        # Both matrices contain normalized vectors.
        matrix = requirement_embeddings @ candidate_embeddings.T

        matched = []
        missing = []
        details = []
        for index, requirement in enumerate(job_requirements):
            best_index = int(matrix[index].argmax())
            best_score = float(matrix[index][best_index])
            candidate_term = candidate_terms[best_index]
            details.append(
                {
                    "requirement": requirement,
                    "candidate_term": candidate_term,
                    "similarity": round(best_score, 4),
                }
            )
            if best_score >= SKILL_MATCH_THRESHOLD:
                if candidate_term not in matched:
                    matched.append(candidate_term)
            elif requirement not in missing:
                missing.append(requirement)

        return matched[:15], missing[:15], details[:30]

    def _embed(self, text: str):
        cache_key = self._cache_key(text)
        with self._cache_lock:
            cached = self._embedding_cache.get(cache_key)
            if cached is not None:
                self._embedding_cache.move_to_end(cache_key)
                return cached

        embedding = self._model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        self._cache_embedding(cache_key, embedding)
        return embedding

    def _embed_many(self, texts: List[str]):
        embeddings = []
        missing_texts = []
        missing_keys = []
        for text in texts:
            key = self._cache_key(text)
            with self._cache_lock:
                cached = self._embedding_cache.get(key)
                if cached is not None:
                    self._embedding_cache.move_to_end(key)
                    embeddings.append(cached)
                    continue
            embeddings.append(None)
            missing_texts.append(text)
            missing_keys.append(key)

        if missing_texts:
            encoded = self._model.encode(
                missing_texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
                batch_size=32,
            )
            encoded_index = 0
            for index, embedding in enumerate(embeddings):
                if embedding is None:
                    value = encoded[encoded_index]
                    self._cache_embedding(missing_keys[encoded_index], value)
                    embeddings[index] = value
                    encoded_index += 1

        import numpy as np

        return np.vstack(embeddings)

    def _cache_embedding(self, key: str, embedding: Any) -> None:
        with self._cache_lock:
            self._embedding_cache[key] = embedding
            self._embedding_cache.move_to_end(key)
            while len(self._embedding_cache) > MAX_CACHE_ITEMS:
                self._embedding_cache.popitem(last=False)

    def _cache_key(self, text: str) -> str:
        payload = f"{self.model_name}\0{text}".encode("utf-8", errors="ignore")
        return hashlib.sha256(payload).hexdigest()

    def _build_explanation(
        self,
        semantic_score: float,
        matched_skills: List[str],
        missing_skills: List[str],
    ) -> str:
        matched_text = ", ".join(matched_skills[:5]) or "no strongly aligned profile terms"
        missing_text = ", ".join(missing_skills[:5]) or "no major semantic gaps detected"
        return (
            f"Embedding similarity is {semantic_score:.0f}%. "
            f"Strongest profile matches: {matched_text}. "
            f"Potential gaps: {missing_text}."
        )

    @staticmethod
    def _clean_phrase(value: Any) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip(" -:\t.")
        return text

    @staticmethod
    def _as_list(value: Any) -> List[Any]:
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    def _flatten_strings(self, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, (int, float)):
            return [str(value)]
        if isinstance(value, dict):
            result = []
            for nested in value.values():
                result.extend(self._flatten_strings(nested))
            return result
        if isinstance(value, Iterable):
            result = []
            for nested in value:
                result.extend(self._flatten_strings(nested))
            return result
        return []


job_match_ai_service = JobMatchAIService()

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from app.services.job_match_ai_service import JobMatchAIService
from app.services.match_score_service import _merge_profile_sources


class JobMatchAIServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = JobMatchAIService()
        self.service._model = SimpleNamespace()
        self.service._model_name = "test/sentence-transformer"
        self.service._load_attempted = True
        self.service._load_error = ""
        self.service._embedding_cache.clear()

    def test_service_is_singleton(self):
        self.assertIs(JobMatchAIService(), JobMatchAIService())

    def test_match_score_is_cosine_similarity_percentage(self):
        profile = {
            "skills": ["Python", "FastAPI"],
            "projects": [{"name": "API platform", "technologies_used": "Python, FastAPI"}],
            "experience": [{"role": "Backend Engineer"}],
            "education": [{"degree": "B.E. Computer Science"}],
            "certifications": [],
        }
        job = SimpleNamespace(
            title="Backend Engineer",
            company="Example",
            description="Build and maintain Python web APIs.",
        )

        with patch.object(self.service, "load_model"), patch.object(
            self.service,
            "_embed",
            side_effect=[
                np.array([1.0, 0.0]),
                np.array([0.8, 0.6]),
            ],
        ), patch.object(
            self.service,
            "_compare_requirements",
            return_value=(
                ["Python", "FastAPI"],
                ["Kubernetes"],
                [{"requirement": "Kubernetes", "candidate_term": "FastAPI", "similarity": 0.2}],
            ),
        ):
            result = self.service.generate_match_score(profile, job)

        self.assertEqual(result["semantic_score"], 80.0)
        self.assertEqual(result["match_score"], 80.0)
        self.assertEqual(result["matched_skills"], ["Python", "FastAPI"])
        self.assertEqual(result["missing_skills"], ["Kubernetes"])

    def test_candidate_and_job_text_are_built_from_real_data(self):
        profile = {
            "skills": ["R", "SQL"],
            "projects": [{"name": "Churn model", "technologies_used": "XGBoost"}],
            "experience": [{"role": "Data Analyst"}],
            "education": [{"degree": "BE CSE"}],
            "certifications": [{"name": "AWS"}],
        }
        job = SimpleNamespace(
            title="Senior Data Analyst",
            company="Example",
            description="Analyze product data and build stakeholder dashboards.",
        )

        candidate_text = self.service.build_candidate_text(profile)
        job_text = self.service.build_job_text(job)

        self.assertIn("R", candidate_text)
        self.assertIn("XGBoost", candidate_text)
        self.assertIn("AWS", candidate_text)
        self.assertIn(job.description, job_text)

    def test_incomplete_parsed_profile_does_not_shadow_user_profile(self):
        user_profile = SimpleNamespace(
            full_name="Rajat",
            location="Bengaluru",
            skills=["SQL", "Power BI"],
            projects=[],
            certifications=[],
            degree="B.E. Computer Science",
            college="Example College",
            graduation_year=2022,
            current_designation="Data Analyst",
            current_company="Example Company",
            years_experience="3 years",
            desired_role="Senior Data Analyst",
        )
        parsed_profile = SimpleNamespace(parsed_profile_json={"test": "working"})

        merged = _merge_profile_sources(parsed_profile, user_profile)

        self.assertEqual(merged["skills"], ["SQL", "Power BI"])
        self.assertEqual(merged["years_of_experience"], "3 years")


if __name__ == "__main__":
    unittest.main()

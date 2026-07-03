import unittest

from fastapi import HTTPException

from app.services.resume_renderer import render_resume
from app.services.resume_tailoring_service import validate_structured_resume


RESUME_JSON = {
    "name": "Rajat Mehta",
    "headline": "Senior Data Analyst",
    "contact": {
        "email": "rajat@example.com",
        "phone": "+91 90000 00000",
        "linkedin": "linkedin.com/in/rajat",
        "github": "github.com/rajat",
        "location": "Bengaluru",
    },
    "summary": "Data analyst specializing in Python, SQL, and reporting.",
    "education": [
        {
            "institution": "Example University",
            "degree": "B.E.",
            "field_of_study": "Computer Science",
            "end_date": "2024",
        }
    ],
    "experience": [
        {
            "company": "Example Analytics",
            "title": "Data Analyst",
            "start_date": "2024",
            "end_date": "Present",
            "bullets": ["Built SQL reporting pipelines."],
        }
    ],
    "projects": [
        {
            "name": "Forecasting Platform",
            "technologies": ["Python", "FastAPI"],
            "bullets": ["Created automated forecasting workflows."],
        }
    ],
    "research": [],
    "certifications": [{"name": "Data Analytics Certificate"}],
    "technical_skills": {
        "languages": ["Python", "SQL"],
        "frameworks": ["FastAPI"],
        "ai_ml": ["Scikit-learn"],
        "automation": ["n8n"],
        "cloud": [],
        "tools": ["Power BI"],
    },
}


class ResumeRendererTests(unittest.TestCase):
    def test_renders_fixed_ats_sections_from_structured_json(self):
        rendered = render_resume(RESUME_JSON)

        self.assertIn("<h1>Rajat Mehta</h1>", rendered)
        self.assertIn("<h2>Professional Summary</h2>", rendered)
        self.assertIn("<h2>Experience</h2>", rendered)
        self.assertIn("<h2>Technical Skills</h2>", rendered)
        self.assertIn("Python, SQL", rendered)
        self.assertNotIn("```", rendered)

    def test_autoescapes_ai_content(self):
        resume = dict(RESUME_JSON)
        resume["summary"] = "<script>alert('x')</script>"

        rendered = render_resume(resume)

        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_extracts_resume_json_from_workflow_response(self):
        workflow_result = {
            "resume_json": RESUME_JSON,
        }

        resume = validate_structured_resume(workflow_result)

        self.assertEqual(resume.name, "Rajat Mehta")
        self.assertEqual(resume.technical_skills.languages, ["Python", "SQL"])

    def test_missing_resume_json_returns_502(self):
        with self.assertRaises(HTTPException) as context:
            validate_structured_resume({"html": "<html>AI generated resume</html>"})

        self.assertEqual(context.exception.status_code, 502)

    def test_invalid_resume_json_returns_422(self):
        with self.assertRaises(HTTPException) as context:
            validate_structured_resume({"resume_json": {"name": ""}})

        self.assertEqual(context.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()

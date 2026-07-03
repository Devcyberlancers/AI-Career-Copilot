import unittest

from app.models.resume_schema import ResumeSchema
from app.services.resume_json_validator import validate_resume_json
from app.services.resume_renderer import render_resume


def sample_resume(role="Data Analyst", years=3, repeated=False):
    first_bullet = "Analyzed SQL datasets across 40 product categories, identifying a 14% revenue leakage pattern."
    second_bullet = (
        "Analyzed SQL datasets across 40 product categories, building a weekly Power BI dashboard for 8 KPIs."
        if repeated
        else "Built a weekly Power BI dashboard for 8 KPIs, reducing manual reporting time from 3 hours to under 15 minutes."
    )
    return {
        "name": "Example Candidate",
        "headline": role,
        "contact": {
            "email": "candidate@example.com",
            "phone": "+91 90000 00000",
            "linkedin": "linkedin.com/in/candidate",
            "github": "github.com/candidate",
            "location": "Bengaluru",
        },
        "summary": (
            f"{role} with hands-on experience across Python, SQL, Power BI, and Tableau. "
            "Built analytics dashboards reducing reporting time from 3 hours to under 15 minutes."
        ),
        "technical_skills": {
            "languages": ["Python", "SQL"],
            "frameworks": ["FastAPI"],
            "ai_ml": ["Scikit-learn"],
            "automation": ["Airflow"],
            "cloud": ["AWS"],
            "tools": ["Power BI", "Tableau", "Excel"],
        },
        "experience": [
            {
                "company": "Example Co",
                "title": role,
                "location": "Bengaluru",
                "start_date": "Jan 2023",
                "end_date": "Jan 2026" if years >= 3 else "Jun 2023",
                "bullets": [
                    first_bullet,
                    second_bullet,
                    "Automated weekly Excel reconciliation checks across seller cohorts, improving data quality for business reviews.",
                    "Delivered stakeholder-ready KPI summaries covering revenue, churn, funnel movement, and operational trends.",
                ],
            },
            {
                "company": "Second Example",
                "title": "Analyst Intern",
                "location": "Remote",
                "start_date": "Jul 2022",
                "end_date": "Dec 2022",
                "bullets": [
                    "Developed Python scripts to clean transaction data and standardize reporting inputs for analysis.",
                    "Identified recurring quality issues in source files and documented validation rules for repeatable workflows.",
                    "Implemented SQL checks for revenue, customer, and product tables to improve reporting reliability.",
                    "Optimized dashboard refresh steps by organizing source extracts and removing duplicated manual work.",
                ],
            }
        ],
        "projects": [
            {
                "name": "Analytics Dashboard",
                "technologies": ["Python", "SQL", "Power BI"],
                "bullets": [
                    "Designed dashboard data models covering 1M rows and improving KPI visibility.",
                    "Delivered drill-down reports for stakeholder reviews using Power BI and SQL.",
                    "Implemented reusable DAX measures for revenue, retention, funnel, and operational performance metrics.",
                    "Optimized report pages for executive review by prioritizing trends, outliers, and actionable insights.",
                ],
            },
            {
                "name": "Customer Churn Model",
                "technologies": ["Python", "Scikit-learn", "SQL"],
                "bullets": [
                    "Built logistic regression features from customer activity, payment behavior, and engagement signals.",
                    "Engineered SQL extracts to profile high-risk customer cohorts and support targeted retention analysis.",
                    "Analyzed model outputs with precision and recall checks to explain churn patterns to stakeholders.",
                    "Delivered concise recommendations for improving early identification of accounts needing intervention.",
                ],
            }
        ],
        "education": [
            {
                "degree": "B.E.",
                "field_of_study": "Computer Science",
                "institution": "Example University",
                "graduation_date": "2024",
                "details": ["CGPA: 8.5 / 10"],
            }
        ],
        "certifications": [{"name": "Data Analytics Certificate", "issuer": "Example", "date": "2024"}],
    }


class ResumeJsonValidatorTests(unittest.TestCase):
    def test_batch_valid_samples_render_and_validate(self):
        samples = [
            sample_resume("Data Analyst", 3),
            sample_resume("Software Engineer", 3),
            sample_resume("Marketing Analyst", 3),
            sample_resume("Data Analyst Intern", 0),
            sample_resume("Business Analyst", 2),
        ]
        report = []
        for index, payload in enumerate(samples):
            resume = ResumeSchema.model_validate(payload)
            validation = validate_resume_json(resume, candidate_profile={"years_of_experience": 3})
            html = render_resume(resume)
            report.append((index, validation.valid, validation.violations))
            self.assertIn("<main class=\"resume\">", html)
            self.assertFalse(validation.violations, report)

    def test_repeated_bullet_opening_is_flagged(self):
        resume = ResumeSchema.model_validate(sample_resume(repeated=True))
        validation = validate_resume_json(resume, candidate_profile={"years_of_experience": 3})
        self.assertFalse(validation.valid)
        self.assertTrue(any("repeats the opening" in item for item in validation.violations))

    def test_senior_title_under_two_years_is_flagged(self):
        payload = sample_resume("Senior Data Analyst", 0)
        resume = ResumeSchema.model_validate(payload)
        validation = validate_resume_json(resume, candidate_profile={"years_of_experience": 0.6})
        self.assertFalse(validation.valid)
        self.assertTrue(any("seniority" in item for item in validation.violations))


if __name__ == "__main__":
    unittest.main()

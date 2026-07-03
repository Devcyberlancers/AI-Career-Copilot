import unittest

from app.utils.resume_parser import (
    count_parsed_fields,
    is_debug_profile,
    parse_resume_text,
)


RESUME_TEXT = """
Rajat Mehta
Data Analyst
Email: rajat.mehta@email.com | Phone: +91 98211 76543 | Location: Pune, Maharashtra
PROFESSIONAL SUMMARY
Data Analyst with hands-on experience in SQL, Python, dashboards, and business analysis.
SKILLS
Languages & Querying: Python, SQL, R
BI & Visualization: Power BI, Tableau, Looker Studio
Tools & Platforms: Git, Jupyter Notebook, Airflow
WORK EXPERIENCE
Data Analyst Intern Jul 2023 - Oct 2023
Meesho | Bengaluru
Built Power BI dashboards and analyzed seller data with SQL and Python.
PROJECTS
Customer Segmentation Sep 2023
Tools: Python | Scikit-learn | Tableau
Applied RFM scoring and KMeans clustering to retail transactions.
EDUCATION
B.E. in Information Technology 2020 - 2024
College of Engineering Pune
CERTIFICATIONS
Google Data Analytics Professional Certificate - Coursera (2023)
Microsoft Power BI Data Analyst Associate - Microsoft (2024)
ADDITIONAL INFORMATION
Languages: English, Hindi, Marathi
"""


class ResumeParserTests(unittest.TestCase):
    def test_parses_structured_candidate_profile(self):
        profile = parse_resume_text(RESUME_TEXT)

        self.assertEqual(profile["name"], "Rajat Mehta")
        self.assertEqual(profile["email"], "rajat.mehta@email.com")
        self.assertIn("98211", profile["phone"])
        self.assertEqual(profile["location"], "Pune, Maharashtra")
        self.assertIn("Python", profile["skills"])
        self.assertIn("Power BI", profile["tools"])
        self.assertEqual(len(profile["experience"]), 1)
        self.assertEqual(len(profile["projects"]), 1)
        self.assertEqual(len(profile["education"]), 1)
        self.assertEqual(len(profile["certifications"]), 2)
        self.assertIn("English", profile["languages"])
        self.assertGreater(count_parsed_fields(profile), 8)
        self.assertIn("Data Analyst with hands-on experience", profile["raw_resume_text"])

    def test_debug_payload_is_rejected(self):
        self.assertTrue(is_debug_profile({"test": "working"}))
        self.assertFalse(is_debug_profile(parse_resume_text(RESUME_TEXT)))


if __name__ == "__main__":
    unittest.main()

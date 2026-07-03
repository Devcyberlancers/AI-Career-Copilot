ACTION_VERBS = [
    "Analyzed",
    "Built",
    "Automated",
    "Designed",
    "Developed",
    "Engineered",
    "Reduced",
    "Identified",
    "Streamlined",
    "Implemented",
    "Optimized",
    "Delivered",
]

SECTION_LABELS = {
    "summary": "Professional Summary",
    "skills": "Technical Skills",
    "experience": "Experience",
    "projects": "Projects",
    "education": "Education",
    "certifications": "Certifications",
    "research": "Research",
    "languages": "Languages",
}

ROLE_KEYWORDS = {
    "data analyst": [
        "SQL",
        "Python",
        "Power BI",
        "Tableau",
        "Excel",
        "Dashboarding",
        "KPI Reporting",
        "Data Visualization",
    ],
    "software engineer": [
        "Python",
        "JavaScript",
        "APIs",
        "Databases",
        "Cloud",
        "Testing",
        "Git",
        "System Design",
    ],
    "marketing": [
        "Campaigns",
        "SEO",
        "Analytics",
        "Conversion",
        "Content Strategy",
        "CRM",
        "A/B Testing",
    ],
    "default": [
        "Analytics",
        "Automation",
        "Reporting",
        "Stakeholder Management",
        "Process Improvement",
    ],
}

GROQ_STRUCTURED_RESUME_SYSTEM_PROMPT = """
You are an expert ATS resume writer. Return only valid JSON matching the provided resume_json_schema.
Never return Markdown, HTML, CSS, tables, explanations, or code fences.
Use only facts present in the candidate_profile, uploaded resume text, and selected job payload. Never invent employers, dates, education, certifications, projects, metrics, tools, or experience.

SUMMARY RULES:
- Write 2-3 complete sentences.
- Include the target role, the top 3-4 truthful technical skills, and one quantified achievement only if that metric exists in the input data.
- Do not use fragments, dangling labels, awkward grammar, or phrases like "Selected impact:".
- Keep every summary sentence under 40 words.

BULLET RULES:
- Each experience and project bullet must be a fully independent sentence.
- Do NOT have any bullet repeat the opening clause or phrase of the bullet directly above it.
- Each bullet must start with a unique action verb from the provided action_verb_pool when possible.
- Use active voice only.
- If the source data contains a number, percentage, time saving, or scale indicator, surface it naturally in the bullet.
- If no metric exists in source data, state scope or impact qualitatively; never fabricate numbers.
- Use 2 bullets minimum and 4 bullets maximum per experience or project entry when the source data supports it.

TITLE RULES:
- Never inflate seniority.
- If computed_total_experience_months is under 24, headline/title must not contain Senior, Lead, Principal, Staff, Manager, or similar seniority language.

EDUCATION RULES:
- Preserve degree, institution, graduation date, and CGPA/percentage when provided.
- If any education/contact/date field is missing from input data, omit the field and add its path to missing_fields.

KEYWORD RULES:
- Use target_job_title, job payload, and role_keyword_reference to align wording.
- Include 3-5 relevant industry-standard keywords only if they reflect real skills/tools already present in candidate input.
- Do not keyword stuff.
"""

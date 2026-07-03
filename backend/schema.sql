-- SQL Schema definition for AI Career Copilot

-- Jobs Table
CREATE TABLE jobs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT,
    description TEXT,
    apply_url TEXT,
    source TEXT,
    status TEXT DEFAULT 'Discovered',
    match_score FLOAT,
    semantic_score FLOAT,
    matched_skills JSON NOT NULL DEFAULT '[]',
    missing_skills JSON NOT NULL DEFAULT '[]',
    matched_tools JSON NOT NULL DEFAULT '[]',
    missing_tools JSON NOT NULL DEFAULT '[]',
    experience_gap FLOAT NOT NULL DEFAULT 0,
    score_breakdown_json JSON NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Candidate Profiles Table
CREATE TABLE candidate_profiles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    parsed_profile_json JSON NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tailored Resumes Table
CREATE TABLE tailored_resumes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    job_title TEXT,
    company TEXT,
    job_description TEXT,
    tailored_resume_text TEXT,
    pdf_path TEXT,
    pdf_url TEXT,
    original_resume_path TEXT,
    tailored_resume_path TEXT,
    original_match_score FLOAT,
    tailored_match_score FLOAT,
    improvement_score FLOAT,
    missing_skills JSON NOT NULL DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Phase 1 Resume Intelligence MVP candidate profile migration.
-- SQLite/dev migration for the local career_copilot.db database.

PRAGMA foreign_keys = OFF;

CREATE TABLE IF NOT EXISTS candidate_profiles_mvp (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE,
    parsed_profile_json JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

INSERT OR REPLACE INTO candidate_profiles_mvp (
    id,
    user_id,
    parsed_profile_json,
    created_at,
    updated_at
)
SELECT
    id,
    user_id,
    json_object(
        'name', COALESCE(name, ''),
        'email', COALESCE(email, ''),
        'phone', COALESCE(phone, ''),
        'location', COALESCE(location, ''),
        'skills', json(COALESCE(skills_json, '[]')),
        'projects', json(COALESCE(projects_json, '[]')),
        'certifications', json(COALESCE(certifications_json, '[]')),
        'experience', json(COALESCE(experience_json, '[]')),
        'education', json(COALESCE(education_json, '[]')),
        'tools', json(COALESCE(tools_json, '[]')),
        'languages', json(COALESCE(languages_json, '[]')),
        'years_experience', COALESCE(years_of_experience, 0),
        'career_level', COALESCE(career_level, ''),
        'summary', COALESCE(summary, '')
    ),
    COALESCE(created_at, CURRENT_TIMESTAMP),
    COALESCE(updated_at, CURRENT_TIMESTAMP)
FROM candidate_profiles;

DROP TABLE IF EXISTS candidate_profiles;

ALTER TABLE candidate_profiles_mvp RENAME TO candidate_profiles;

CREATE UNIQUE INDEX IF NOT EXISTS ix_candidate_profiles_user_id
ON candidate_profiles(user_id);

CREATE INDEX IF NOT EXISTS ix_candidate_profiles_id
ON candidate_profiles(id);

PRAGMA foreign_keys = ON;

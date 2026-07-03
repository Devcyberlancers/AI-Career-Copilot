import os
import threading
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database.connection import Base, engine
from app import models
from app.routes import auth, dashboard, admin, admin_cleanup, resume, profile, jobs, candidate_profile, notifications
from sqlalchemy import text
from app.services.job_match_ai_service import job_match_ai_service
from app.services.limits_service import ensure_platform_limits
from app.services.job_search_scheduler import start_job_search_scheduler

# Ensure uploads directory exists on startup
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Automatically create database tables if they do not exist
Base.metadata.create_all(bind=engine)

# Auto-migration check: ensure is_admin column exists
try:
    with engine.begin() as conn:
        conn.execute(text("SELECT is_admin FROM users LIMIT 1"))
except Exception:
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE NOT NULL"))
            print("Auto-migration: Added is_admin column to users table.")
    except Exception as e:
        print(f"Auto-migration failed: {e}")


# Auto-migration check: ensure email verification columns exist
user_email_migrations = [
    ("email_verified", "BOOLEAN DEFAULT FALSE NOT NULL"),
    ("email_verified_at", "DATETIME"),
]
for column_name, column_definition in user_email_migrations:
    try:
        with engine.begin() as conn:
            conn.execute(text(f"SELECT {column_name} FROM users LIMIT 1"))
    except Exception:
        try:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {column_name} {column_definition}"))
                print(f"Auto-migration: Added {column_name} column to users table.")
        except Exception as e:
            print(f"Auto-migration failed for users.{column_name}: {e}")

# Auto-migration check: ensure match_score column exists in jobs
try:
    with engine.begin() as conn:
        conn.execute(text("SELECT match_score FROM jobs LIMIT 1"))
except Exception:
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN match_score FLOAT"))
            print("Auto-migration: Added match_score column to jobs table.")
    except Exception as e:
        print(f"Auto-migration failed for match_score: {e}")

# Auto-migration check: ensure explainable ATS match fields exist in jobs
job_match_migrations = [
    ("semantic_score", "FLOAT"),
    ("confidence", "FLOAT"),
    ("matched_skills", "JSON DEFAULT '[]' NOT NULL"),
    ("missing_skills", "JSON DEFAULT '[]' NOT NULL"),
    ("matched_tools", "JSON DEFAULT '[]' NOT NULL"),
    ("missing_tools", "JSON DEFAULT '[]' NOT NULL"),
    ("experience_gap", "FLOAT DEFAULT 0 NOT NULL"),
    ("score_breakdown_json", "JSON DEFAULT '{}' NOT NULL"),
]
for column_name, column_definition in job_match_migrations:
    try:
        with engine.begin() as conn:
            conn.execute(text(f"SELECT {column_name} FROM jobs LIMIT 1"))
    except Exception:
        try:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {column_name} {column_definition}"))
                print(f"Auto-migration: Added {column_name} column to jobs table.")
        except Exception as e:
            print(f"Auto-migration failed for jobs.{column_name}: {e}")

# Auto-migration check: ensure desired_role column exists in users
try:
    with engine.begin() as conn:
        conn.execute(text("SELECT desired_role FROM users LIMIT 1"))
except Exception:
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN desired_role VARCHAR"))
            print("Auto-migration: Added desired_role column to users table.")
    except Exception as e:
        print(f"Auto-migration failed for desired_role: {e}")

# Auto-migration check: ensure location column exists in users
try:
    with engine.begin() as conn:
        conn.execute(text("SELECT location FROM users LIMIT 1"))
except Exception:
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN location VARCHAR"))
            print("Auto-migration: Added location column to users table.")
    except Exception as e:
        print(f"Auto-migration failed for location: {e}")

# Auto-migration check: ensure skills column exists in users
try:
    with engine.begin() as conn:
        conn.execute(text("SELECT skills FROM users LIMIT 1"))
except Exception:
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN skills TEXT"))
            print("Auto-migration: Added skills column to users table.")
    except Exception as e:
        print(f"Auto-migration failed for skills: {e}")


# Auto-migration check: ensure scheduled job search settings exist
application_settings_search_migrations = [
    ("daily_job_search_enabled", "BOOLEAN DEFAULT FALSE NOT NULL"),
    ("daily_job_search_time", "VARCHAR DEFAULT '09:00' NOT NULL"),
    ("daily_job_search_platforms", "JSON DEFAULT '[]' NOT NULL"),
    ("jobs_per_platform", "INTEGER DEFAULT 20 NOT NULL"),
    ("last_daily_job_search_at", "DATETIME"),
]
for column_name, column_definition in application_settings_search_migrations:
    try:
        with engine.begin() as conn:
            conn.execute(text(f"SELECT {column_name} FROM application_settings LIMIT 1"))
    except Exception:
        try:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE application_settings ADD COLUMN {column_name} {column_definition}"))
                print(f"Auto-migration: Added {column_name} column to application_settings table.")
        except Exception as e:
            print(f"Auto-migration failed for application_settings.{column_name}: {e}")

# Auto-migration check: ensure Resume Intelligence MVP JSON column exists
try:
    with engine.begin() as conn:
        conn.execute(text("SELECT parsed_profile_json FROM candidate_profiles LIMIT 1"))
except Exception:
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE candidate_profiles ADD COLUMN parsed_profile_json JSON DEFAULT '{}' NOT NULL"))
            print("Auto-migration: Added parsed_profile_json column to candidate_profiles table.")
    except Exception as e:
        print(f"Auto-migration failed for candidate_profiles.parsed_profile_json: {e}")

# Auto-migration check: ensure Resume Tailoring storage columns exist
tailored_resume_migrations = [
    ("job_title", "VARCHAR"),
    ("company", "VARCHAR"),
    ("job_description", "TEXT"),
    ("tailored_resume_text", "TEXT"),
    ("pdf_path", "VARCHAR"),
    ("pdf_url", "VARCHAR"),
    ("before_score", "FLOAT"),
    ("after_score", "FLOAT"),
    ("improvement", "FLOAT"),
    ("matched_keywords", "JSON DEFAULT '[]' NOT NULL"),
    ("missing_keywords", "JSON DEFAULT '[]' NOT NULL"),
    ("sections_modified", "JSON DEFAULT '[]' NOT NULL"),
    ("resume_used", "VARCHAR"),
    ("recommendation", "TEXT"),
    ("reason", "TEXT"),
    ("confidence", "FLOAT"),
]
for column_name, column_definition in tailored_resume_migrations:
    try:
        with engine.begin() as conn:
            conn.execute(text(f"SELECT {column_name} FROM tailored_resumes LIMIT 1"))
    except Exception:
        try:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE tailored_resumes ADD COLUMN {column_name} {column_definition}"))
                print(f"Auto-migration: Added {column_name} column to tailored_resumes table.")
        except Exception as e:
            print(f"Auto-migration failed for tailored_resumes.{column_name}: {e}")

app = FastAPI(
    title="AI Career Copilot API",
    description="Authentication and Dashboard API for AI Career Copilot platform.",
    version="1.0.0"
)


@app.on_event("startup")
def load_job_match_model():
    _validate_production_config()

    try:
        from app.database.connection import SessionLocal
        db = SessionLocal()
        try:
            ensure_platform_limits(db)
        finally:
            db.close()
    except Exception as exc:
        print(f"Platform limit initialization failed: {exc}")

    def load():
        try:
            job_match_ai_service.load_model()
        except Exception as exc:
            print(f"Job match embedding model startup failed: {exc}")

    threading.Thread(target=load, name="job-match-model-loader", daemon=True).start()
    start_job_search_scheduler()

def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _is_production() -> bool:
    return os.getenv("ENVIRONMENT", "development").strip().lower() in {"production", "prod"}


def _validate_production_config() -> None:
    if not _is_production():
        return

    required = [
        "DATABASE_URL",
        "JWT_SECRET",
        "BASE_API_URL",
        "CORS_ORIGINS",
        "RESUME_TAILORING_WEBHOOK_URL",
        "RESUME_INTELLIGENCE_WEBHOOK_URL",
    ]
    missing = [name for name in required if not os.getenv(name, "").strip()]
    if missing:
        raise RuntimeError(f"Missing required production env vars: {', '.join(missing)}")

    unsafe_values = []
    if os.getenv("DATABASE_URL", "").startswith("sqlite"):
        unsafe_values.append("DATABASE_URL must use PostgreSQL in production")
    if "localhost" in os.getenv("BASE_API_URL", "") or "127.0.0.1" in os.getenv("BASE_API_URL", ""):
        unsafe_values.append("BASE_API_URL must be public in production")
    if "webhook-test" in os.getenv("RESUME_TAILORING_WEBHOOK_URL", ""):
        unsafe_values.append("RESUME_TAILORING_WEBHOOK_URL must use n8n production /webhook URL")
    if "webhook-test" in os.getenv("RESUME_INTELLIGENCE_WEBHOOK_URL", ""):
        unsafe_values.append("RESUME_INTELLIGENCE_WEBHOOK_URL must use n8n production /webhook URL")
    if os.getenv("JWT_SECRET") in {"copilot_jwt_secret_dev_key_2026_xYz987", "super_secret_key_change_me_in_production_12345"}:
        unsafe_values.append("JWT_SECRET must be replaced for production")
    if _env_bool("ENABLE_DEV_ADMIN_ROUTES", "false"):
        unsafe_values.append("ENABLE_DEV_ADMIN_ROUTES must be false in production")
    if unsafe_values:
        raise RuntimeError("Unsafe production config: " + "; ".join(unsafe_values))


def _cors_origins() -> list[str]:
    configured = os.getenv("CORS_ORIGINS", "").strip()
    if configured:
        return [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]
    if _is_production():
        print("WARNING: CORS_ORIGINS is empty in production. Browser API calls will be blocked.")
        return []
    return ["http://localhost:3000", "http://127.0.0.1:3000"]


# Configure CORS so frontend can communicate with the backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="", tags=["Authentication"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
if _env_bool("ENABLE_DEV_ADMIN_ROUTES", "false"):
    app.include_router(admin_cleanup.router, prefix="/api/admin", tags=["Development Admin"])
app.include_router(resume.router, prefix="/api/resume", tags=["Resume"])
app.include_router(profile.router, prefix="/api/profile", tags=["Profile"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["Jobs"])
app.include_router(candidate_profile.router, prefix="/api/candidate-profile", tags=["Candidate Profile"])
app.include_router(notifications.router, prefix="/api", tags=["Notifications and Settings"])

@app.get("/")
def read_root():
    return {"message": "AI Career Copilot API is running"}

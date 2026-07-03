import os
import sys

from sqlalchemy import create_engine, or_
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.models.job import Job
from app.utils.job_source import SUPPORTED_JOB_SOURCE, is_valid_naukri_url


DEMO_COMPANIES = [
    "Google India",
    "Microsoft India",
    "Amazon",
    "Netflix",
    "Meta Research",
]


def main() -> None:
    database_url = os.getenv("DATABASE_URL", "sqlite:///./career_copilot.db")
    engine = create_engine(database_url)
    session = sessionmaker(bind=engine)()

    try:
        company_filters = [Job.company.ilike(f"%{company}%") for company in DEMO_COMPANIES]
        candidates = session.query(Job).filter(
            or_(
                Job.source != SUPPORTED_JOB_SOURCE,
                Job.source.is_(None),
                Job.apply_url.is_(None),
                *company_filters,
            )
        ).all()

        candidates.extend(
            job
            for job in session.query(Job).filter(Job.source == SUPPORTED_JOB_SOURCE).all()
            if not is_valid_naukri_url(job.apply_url)
        )

        unique_jobs = {job.id: job for job in candidates}
        if not unique_jobs:
            print("No demo, non-Naukri, or invalid-url jobs found.")
            return

        print("Removing invalid jobs:")
        for job in unique_jobs.values():
            print(f"- #{job.id}: {job.title} | {job.company} | {job.source} | {job.apply_url}")
            session.delete(job)

        session.commit()
        print(f"Removed {len(unique_jobs)} invalid job(s).")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()

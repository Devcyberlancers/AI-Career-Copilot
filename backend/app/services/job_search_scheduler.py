import datetime
import logging
import os
import threading
import time
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.models.application_settings import ApplicationSettings
from app.models.user import User
from app.utils.job_source import SUPPORTED_JOB_SOURCES, is_supported_job_source

logger = logging.getLogger("app.services.job_search_scheduler")
SCHEDULER_INTERVAL_SECONDS = int(os.getenv("JOB_SEARCH_SCHEDULER_INTERVAL_SECONDS", "60"))
ENABLE_SCHEDULER = os.getenv("ENABLE_JOB_SEARCH_SCHEDULER", "true").strip().lower() in {"1", "true", "yes", "on"}


def _parse_hhmm(value: str) -> Optional[datetime.time]:
    try:
        hour, minute = [int(part) for part in (value or "09:00").split(":", 1)]
        return datetime.time(hour=hour, minute=minute)
    except Exception:
        return None


def _already_ran_today(settings: ApplicationSettings, now: datetime.datetime) -> bool:
    last = settings.last_daily_job_search_at
    return bool(last and last.date() == now.date())


def _due(settings: ApplicationSettings, now: datetime.datetime) -> bool:
    if not settings.daily_job_search_enabled:
        return False
    scheduled_time = _parse_hhmm(settings.daily_job_search_time)
    if not scheduled_time:
        logger.warning("Invalid daily job search time for user %s: %s", settings.user_id, settings.daily_job_search_time)
        return False
    if _already_ran_today(settings, now):
        return False
    return now.time().replace(second=0, microsecond=0) >= scheduled_time


def _platforms(settings: ApplicationSettings) -> Iterable[str]:
    configured = settings.daily_job_search_platforms or []
    if not configured:
        return SUPPORTED_JOB_SOURCES
    return [source for source in configured if is_supported_job_source(source)]


def run_due_scheduled_job_searches() -> dict:
    # Import inside the function to avoid circular imports during FastAPI startup.
    from app.routes.jobs import execute_discovery_for_source

    now = datetime.datetime.now()
    db: Session = SessionLocal()
    triggered = 0
    try:
        settings_rows = db.query(ApplicationSettings).filter(
            ApplicationSettings.daily_job_search_enabled == True,  # noqa: E712
        ).all()
        for settings in settings_rows:
            if not _due(settings, now):
                continue
            user = db.query(User).filter(User.id == settings.user_id).first()
            if not user:
                continue
            logger.info(
                "Running scheduled daily job search user=%s time=%s platforms=%s",
                user.id,
                settings.daily_job_search_time,
                list(_platforms(settings)),
            )
            for platform in _platforms(settings):
                try:
                    execute_discovery_for_source(
                        db,
                        user,
                        platform,
                        max_results_override=max(1, min(settings.jobs_per_platform or 20, 20)),
                    )
                    triggered += 1
                except Exception as exc:  # noqa: BLE001 - scheduler must continue for other platforms/users
                    logger.exception("Scheduled job search failed user=%s platform=%s: %s", user.id, platform, exc)
            settings.last_daily_job_search_at = now
            db.commit()
    finally:
        db.close()
    return {"triggered_platform_searches": triggered}


def start_job_search_scheduler() -> None:
    if not ENABLE_SCHEDULER:
        logger.info("Job search scheduler disabled by ENABLE_JOB_SEARCH_SCHEDULER=false")
        return

    def loop() -> None:
        logger.info("Job search scheduler started interval=%ss", SCHEDULER_INTERVAL_SECONDS)
        while True:
            try:
                run_due_scheduled_job_searches()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Job search scheduler cycle failed: %s", exc)
            time.sleep(SCHEDULER_INTERVAL_SECONDS)

    thread = threading.Thread(target=loop, name="job-search-scheduler", daemon=True)
    thread.start()

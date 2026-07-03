import datetime
from typing import Dict, Iterable, List
from sqlalchemy.orm import Session
from app.models.limits import DailyLimit, PlatformLimit

DEFAULT_PLATFORMS = ["Naukri", "LinkedIn", "Indeed", "Foundit", "Wellfound", "Cutshort", "Hirist"]
DEFAULT_PLATFORM_LIMIT = 20
DEFAULT_TAILORING_LIMIT = 5


def next_reset_at() -> datetime.datetime:
    tomorrow = datetime.datetime.utcnow().date() + datetime.timedelta(days=1)
    return datetime.datetime.combine(tomorrow, datetime.time.min)


def ensure_platform_limits(db: Session, platforms: Iterable[str] = DEFAULT_PLATFORMS) -> None:
    existing = {row.platform for row in db.query(PlatformLimit).all()}
    for platform in platforms:
        if platform not in existing:
            db.add(PlatformLimit(platform=platform, daily_search_limit=DEFAULT_PLATFORM_LIMIT))
    db.commit()


def get_or_create_daily_limit(db: Session, user_id: int, limit_type: str, platform: str, limit_count: int) -> DailyLimit:
    today = datetime.date.today()
    row = db.query(DailyLimit).filter(
        DailyLimit.user_id == user_id,
        DailyLimit.limit_type == limit_type,
        DailyLimit.platform == platform,
        DailyLimit.date == today,
    ).first()
    if row:
        return row
    row = DailyLimit(
        user_id=user_id,
        limit_type=limit_type,
        platform=platform,
        date=today,
        used_count=0,
        limit_count=limit_count,
        reset_at=next_reset_at(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_usage_limits(db: Session, user_id: int) -> List[Dict]:
    ensure_platform_limits(db)
    platform_rows = db.query(PlatformLimit).order_by(PlatformLimit.platform.asc()).all()
    results = []
    for platform in platform_rows:
        row = get_or_create_daily_limit(db, user_id, "job_search", platform.platform, platform.daily_search_limit)
        results.append({
            "platform": platform.platform,
            "used": row.used_count,
            "limit": row.limit_count,
            "remaining": max(0, row.limit_count - row.used_count),
            "reset_at": row.reset_at,
        })
    tailoring = get_or_create_daily_limit(db, user_id, "resume_tailoring", "global", DEFAULT_TAILORING_LIMIT)
    results.append({
        "platform": "Resume Tailoring",
        "used": tailoring.used_count,
        "limit": tailoring.limit_count,
        "remaining": max(0, tailoring.limit_count - tailoring.used_count),
        "reset_at": tailoring.reset_at,
    })
    return results

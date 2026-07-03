import logging
import os
from datetime import datetime
from typing import Optional

import requests
from sqlalchemy.orm import Session

from app.models.profile import UserProfile
from app.models.resume import Resume
from app.models.user import User

logger = logging.getLogger("app.utils.resume_intelligence")

RESUME_INTELLIGENCE_WEBHOOK_URL = os.getenv(
    "RESUME_INTELLIGENCE_WEBHOOK_URL",
    "",
)
N8N_VERIFY_SSL = os.getenv("N8N_VERIFY_SSL", "true").strip().lower() not in {"0", "false", "no", "off"}


def send_resume_intelligence_webhook(
    user: User,
    resume: Resume,
    resume_text: str,
    db: Session,
    profile: Optional[UserProfile] = None,
    event: str = "resume_uploaded",
):
    profile = profile or db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    payload = {
        "event": event,
        "user_id": user.id,
        "full_name": profile.full_name if profile else user.name,
        "email": user.email,
        "location": profile.location if profile else user.location,
        "desired_role": profile.desired_role if profile else user.desired_role,
        "resume_filename": resume.file_name,
        "resume_text": resume_text,
        "timestamp": datetime.utcnow().isoformat(),
    }

    if not RESUME_INTELLIGENCE_WEBHOOK_URL:
        logger.warning("Resume Intelligence webhook URL is not configured; skipping n8n trigger.")
        return

    try:
        logger.info("Sending extracted resume text to Resume Intelligence Engine")
        logger.info(f"Sending Resume Intelligence webhook for user {user.id}")
        logger.info(f"Resume Intelligence webhook URL: {RESUME_INTELLIGENCE_WEBHOOK_URL}")
        response = requests.post(
            RESUME_INTELLIGENCE_WEBHOOK_URL,
            json=payload,
            timeout=10,
            verify=N8N_VERIFY_SSL,
        )
        response.raise_for_status()
        logger.info("Resume Intelligence webhook sent successfully")
    except Exception as e:
        logger.error(f"Resume Intelligence webhook failed: {e}")

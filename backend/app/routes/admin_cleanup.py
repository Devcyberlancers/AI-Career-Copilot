from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.tailored_resume import TailoredResume
from app.models.user import User
from app.routes.admin import require_admin

router = APIRouter()


@router.delete("/clear-tailored-resumes")
def clear_tailored_resumes(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    deleted_count = db.query(TailoredResume).delete(synchronize_session=False)
    db.commit()

    return {
        "success": True,
        "deleted_count": deleted_count,
        "message": f"Deleted {deleted_count} tailored resume record(s).",
    }

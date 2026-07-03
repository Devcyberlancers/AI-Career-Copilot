import os
import sys


BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from app.database.connection import SessionLocal
from app.models.tailored_resume import TailoredResume


def main() -> int:
    db = SessionLocal()
    try:
        total_found = db.query(TailoredResume).count()
        print(f"Total tailored resume records found: {total_found}")

        deleted_count = db.query(TailoredResume).delete(synchronize_session=False)
        db.commit()

        print(f"Total tailored resume records deleted: {deleted_count}")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"Cleanup failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

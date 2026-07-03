import os
import sys

from sqlalchemy import MetaData, Table, delete, or_, select


BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from app.database.connection import SessionLocal, engine
from app.models.tailored_resume import TailoredResume


CORRUPTED_URL_COLUMNS = ("pdf_url", "preview_url", "download_url")


def main() -> int:
    db = SessionLocal()
    try:
        table = Table(
            TailoredResume.__tablename__,
            MetaData(),
            autoload_with=engine,
        )
        available_url_columns = [
            table.c[column_name]
            for column_name in CORRUPTED_URL_COLUMNS
            if column_name in table.c
        ]

        if not available_url_columns:
            print("No tailored resume URL columns were found. Nothing was deleted.")
            return 0

        corrupted_condition = or_(
            *(column.contains("{{") for column in available_url_columns)
        )
        record_ids = list(
            db.execute(
                select(table.c.id)
                .where(corrupted_condition)
                .order_by(table.c.id)
            ).scalars()
        )

        print(f"Total corrupted tailored resume records found: {len(record_ids)}")
        for record_id in record_ids:
            print(f"Deleting tailored resume record ID: {record_id}")

        if record_ids:
            db.execute(delete(table).where(table.c.id.in_(record_ids)))
        db.commit()

        print(f"Total corrupted tailored resume records deleted: {len(record_ids)}")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"Cleanup failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

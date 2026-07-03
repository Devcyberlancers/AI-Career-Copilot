import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add the parent directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.models.job import Job

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./career_copilot.db")
print(f"Connecting to database: {DATABASE_URL}")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
session = SessionLocal()

try:
    print("Deleting all jobs from the database...")
    num_deleted = session.query(Job).delete()
    session.commit()
    print(f"Successfully deleted {num_deleted} job(s) from the jobs table.")
except Exception as e:
    session.rollback()
    print(f"Error clearing jobs: {e}")
finally:
    session.close()

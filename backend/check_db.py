import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add the parent directory to Python path so we can import app modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.models.user import User

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./career_copilot.db")

print(f"Connecting to database: {DATABASE_URL}")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
session = SessionLocal()

print("\n=== Registered Users in Database ===")
try:
    users = session.query(User).all()
    if not users:
        print("No users found in the database.")
    else:
        print(f"Found {len(users)} user(s):")
        for i, user in enumerate(users, 1):
            print(f"{i}. ID: {user.id} | Name: {user.name} | Email: {user.email} | Admin: {user.is_admin} | Created At: {user.created_at}")
except Exception as e:
    print(f"Error querying database: {e}")
finally:
    session.close()
print("====================================\n")

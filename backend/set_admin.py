import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add the parent directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.models.user import User
from app.auth.security import hash_password

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./career_copilot.db")
print(f"Connecting to database: {DATABASE_URL}")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
session = SessionLocal()

try:
    # 1. Reset password for vikasv.ckm@gmail.com (ID: 1)
    admin_user = session.query(User).filter(User.email == "vikasv.ckm@gmail.com").first()
    if admin_user:
        new_pwd = "admin12345"
        admin_user.password_hash = hash_password(new_pwd)
        admin_user.is_admin = True
        print(f"Successfully reset password for vikasv.ckm@gmail.com to: '{new_pwd}'")
    else:
        print("Admin user vikasv.ckm@gmail.com not found.")

    # 2. Demote deer@gmail.com (ID: 11) from Admin
    deer_user = session.query(User).filter(User.email == "deer@gmail.com").first()
    if deer_user:
        deer_user.is_admin = False
        print("Successfully demoted deer@gmail.com from Admin status.")
    else:
        print("User deer@gmail.com not found.")

    session.commit()
    print("Database updates saved successfully!")

except Exception as e:
    session.rollback()
    print(f"Error updating database: {e}")
finally:
    session.close()

import os
import sqlite3
from datetime import datetime

def check_jobs():
    # Robust path resolution to locate the SQLite database relative to the script location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "backend", "career_copilot.db")
    
    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check job count
        cursor.execute("SELECT COUNT(*) FROM jobs")
        count = cursor.fetchone()[0]
        print("========================================")
        print(f"Jobs Found: {count}")
        print("========================================")
        
        if count == 0:
            print("No jobs stored in the database.")
            return

        # Fetch job details
        cursor.execute("SELECT id, title, company, source, status, created_at FROM jobs ORDER BY id ASC")
        jobs = cursor.fetchall()
        
        # Define table headers
        header = f"{'Job ID':<8} | {'Title':<35} | {'Company':<25} | {'Source':<10} | {'Status':<12} | {'Created Date':<20}"
        print(header)
        print("-" * len(header))
        
        for job in jobs:
            job_id, title, company, source, status, created_at = job
            # Truncate strings for output display if they exceed the column width
            title_disp = title[:33] + ".." if len(title) > 35 else title
            company_disp = company[:23] + ".." if len(company) > 25 else company
            source_disp = str(source)[:10]
            status_disp = str(status)[:12]
            created_disp = str(created_at)[:19]
            
            print(f"{job_id:<8} | {title_disp:<35} | {company_disp:<25} | {source_disp:<10} | {status_disp:<12} | {created_disp:<20}")
            
    except Exception as e:
        print(f"An error occurred querying the jobs table: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_jobs()

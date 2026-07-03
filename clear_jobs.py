import os
import sqlite3

def clear_jobs():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "backend", "career_copilot.db")
    
    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check current count
        cursor.execute("SELECT COUNT(*) FROM jobs")
        before_count = cursor.fetchone()[0]
        
        if before_count == 0:
            print("No jobs to clear. Jobs table is already empty.")
            return

        # Perform deletion
        cursor.execute("DELETE FROM jobs")
        conn.commit()
        
        # Verify deletion count
        print(f"Successfully deleted {before_count} job(s) from the database.")
        
    except Exception as e:
        print(f"An error occurred while clearing jobs: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    clear_jobs()

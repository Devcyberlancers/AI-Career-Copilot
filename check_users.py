import os
import sqlite3

def check_users():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "backend", "career_copilot.db")
    
    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check user count
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        print("========================================")
        print(f"User Count: {count}")
        print("========================================")
        
        if count == 0:
            print("No users registered in the database.")
            return

        # Fetch user details
        cursor.execute("SELECT id, email, is_admin FROM users ORDER BY id ASC")
        users = cursor.fetchall()
        
        # Define table headers
        header = f"{'User ID':<10} | {'Email':<40} | {'Admin Status':<12}"
        print(header)
        print("-" * len(header))
        
        for user in users:
            user_id, email, is_admin = user
            is_admin_str = "Yes" if is_admin else "No"
            print(f"{user_id:<10} | {email:<40} | {is_admin_str:<12}")
            
    except Exception as e:
        print(f"An error occurred querying the users table: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_users()

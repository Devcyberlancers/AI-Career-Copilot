# check_jobs.py

import sqlite3

conn = sqlite3.connect("career_copilot.db")

cursor = conn.cursor()

cursor.execute("""
SELECT
id,
title,
company,
source,
status
FROM jobs
LIMIT 20
""")

rows = cursor.fetchall()

print(f"Found {len(rows)} jobs")

for row in rows:
    print(row)

conn.close()
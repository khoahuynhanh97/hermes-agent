import sqlite3
conn = sqlite3.connect('D:/HermesData/hermes.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("SELECT id, status, revision, duration_seconds, angle FROM affiliate_content_packages ORDER BY created_at")
for r in cursor.fetchall():
    print(f"  pkg {r['id'][:20]}... status={r['status']} dur={r['duration_seconds']}s angle={r['angle'][:40]}")
conn.close()

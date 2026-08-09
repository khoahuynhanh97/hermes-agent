import sqlite3
conn = sqlite3.connect('D:/HermesData/hermes.db')
cursor = conn.cursor()
tables = ['affiliate_products', 'affiliate_research_runs', 'affiliate_product_snapshots', 'affiliate_references', 'affiliate_content_ideas', 'affiliate_content_packages', 'affiliate_approval_events', 'affiliate_run_products', 'affiliate_projection_outbox', 'affiliate_research_briefs', 'affiliate_projection_items', 'affiliate_jobs', 'affiliate_stats']
for table in tables:
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
    exists = cursor.fetchone() is not None
    if exists:
        cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
        count = cursor.fetchone()[0]
        print(f'  [+] {table}: {count} rows')
    else:
        print(f'  [-] {table}: MISSING')
conn.close()

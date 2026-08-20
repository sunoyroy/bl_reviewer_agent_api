import psycopg2, os
from dotenv import load_dotenv
load_dotenv()
conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    port=os.getenv('DB_PORT', '5432'),
    dbname=os.getenv('DB_NAME', 'postgres'),
    user=os.getenv('DB_USER', 'postgres'),
    password=os.getenv('DB_PASS', '')
)
cur = conn.cursor()
cur.execute("""
SELECT column_name
FROM information_schema.columns
WHERE table_schema = 'im_dwh_rpt' AND table_name = 'fact_pc_item'
""")
cols = [row[0] for row in cur.fetchall()]
print("fact_pc_item columns:", cols)

import os
import psycopg2
from dotenv import load_dotenv

def test_connection():
    load_dotenv()
    
    try:
        print("Connecting to the database...")
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            dbname=os.getenv("DB_NAME", "postgres"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASS", "")
        )
        print("Connection successful!")
        
        with conn.cursor() as cur:
            print("Running a simple SELECT query for 10 rows...")
            cur.execute("SELECT eto_ofr_display_id, eto_ofr_title FROM im_dwh_rpt.fact_eto_ofr_live LIMIT 10;")
            rows = cur.fetchall()
            
            print(f"Fetched {len(rows)} rows:")
            for row in rows:
                print(row)
                
    except Exception as e:
        print(f"Database connection or query failed: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    test_connection()

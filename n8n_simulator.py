import os
import json
import datetime
import requests
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Vercel API endpoint
API_URL = "https://bl-reviewer-agent-api-psi.vercel.app/review"

# Database connection parameters
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "")

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

def fetch_leads():
    # Calculate yesterday's date to match N8N logic: {{ $now.minus({ days: 1 }).toFormat('yyyy-MM-dd') }}
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"Fetching leads for date: {yesterday}")

    # Note: Double curly braces {{ }} are used to escape single braces for Python's f-string parsing where necessary.
    query = f"""
    WITH filtered_offers AS (
        SELECT
            feo.eto_ofr_display_id,
            feo.eto_ofr_title,
            dgm.glcat_mcat_name
        FROM (
            SELECT
                eto_ofr_display_id,
                eto_ofr_title,
                eto_ofr_modrefid,
                eto_ofr_mcat_id,
                eto_ofr_approv_date_orig
            FROM im_dwh_rpt.fact_eto_ofr_expired
            WHERE DATE(eto_ofr_approv_date_orig) = DATE '{yesterday}'
              AND eto_leap_emp_id = '-14'

            UNION ALL

            SELECT
                eto_ofr_display_id,
                eto_ofr_title,
                eto_ofr_modrefid,
                eto_ofr_mcat_id,
                eto_ofr_approv_date_orig
            FROM im_dwh_rpt.fact_eto_ofr_live
            WHERE DATE(eto_ofr_approv_date_orig) = DATE '{yesterday}'
              AND eto_leap_emp_id = '-14'
        ) feo
        JOIN im_dwh_rpt.fact_pc_item fpi
            ON feo.eto_ofr_modrefid = fpi.pc_item_display_id
        LEFT JOIN im_dwh_rpt.fact_pc_item_to_glcat_mcat fpitgm
            ON fpi.pc_item_id = fpitgm.fk_pc_item_id
        LEFT JOIN im_dwh_rpt.dim_glcat_mcat dgm
            ON feo.eto_ofr_mcat_id = dgm.glcat_mcat_id
        WHERE fpitgm.fk_pc_item_id IS NULL
          AND dgm.glcat_mcat_name IS NOT NULL
          AND LOWER(TRIM(feo.eto_ofr_title)) <> LOWER(TRIM(dgm.glcat_mcat_name))
    ),

    attribute_data AS (
        SELECT
            fk_eto_ofr_display_id,
            REPLACE(COALESCE(fk_im_spec_master_desc,''), '"', '\\"') AS question,
            REPLACE(COALESCE(fk_im_spec_options_desc,''), '"', '\\"') AS answer
        FROM im_dwh_rpt.fact_eto_attribute
        WHERE eto_attribute_source BETWEEN 1 AND 199
           OR eto_attribute_source IN (204,205,206,208,210,215,218,220,221,250,991,999)
    )

    SELECT
        fo.eto_ofr_display_id AS offer_id,
        fo.eto_ofr_title AS title,
        fo.glcat_mcat_name AS mcat,
        COALESCE(
            '{{' ||
            LISTAGG(
                '"' || ad.question || '":"' || ad.answer || '"',
                ','
            ) WITHIN GROUP (ORDER BY ad.question)
            || '}}',
            '{{}}'
        ) AS isq_filled
    FROM filtered_offers fo
    LEFT JOIN attribute_data ad
        ON fo.eto_ofr_display_id = ad.fk_eto_ofr_display_id
    GROUP BY
        fo.eto_ofr_display_id,
        fo.eto_ofr_title,
        fo.glcat_mcat_name
    ORDER BY
        random()
    LIMIT 100;
    """

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(query)
            rows = cur.fetchall()
            # Convert DictRow to standard dict
            return [dict(row) for row in rows]
    finally:
        conn.close()


def process_lead(lead, date_str):
    offer_id = lead.get('offer_id', '')
    title = lead.get('title', '')
    mcat = lead.get('mcat', '')
    isq_filled_raw = lead.get('isq_filled', '{}')
    
    # Try parsing the ISQ json string from the DB if possible
    try:
        isq_filled = json.loads(isq_filled_raw)
    except Exception:
        isq_filled = {}

    payload = {
        "offer_id": offer_id,
        "title": title,
        "mcat": mcat,
        "isq_filled": isq_filled
    }

    try:
        response = requests.post(API_URL, json=payload, timeout=60)
        response.raise_for_status()
        api_result = response.json()
    except Exception as e:
        print(f"API request failed for offer_id {offer_id}: {e}")
        api_result = {
            "flags": [],
            "concise_reason": f"API Error: {str(e)}",
            "overall_confidence": None
        }

    # Map the output just like the N8N Google Sheets Node mapping
    return {
        "OfferID": offer_id,
        "Title": title,
        "MCAT": mcat,
        "Date": date_str,
        "Flags": api_result.get("flags", []),
        "reason": api_result.get("concise_reason", ""),
        "ISQ": isq_filled_raw,
        "confidence": api_result.get("overall_confidence", None)
    }


def main():
    try:
        leads = fetch_leads()
        print(f"Successfully fetched {len(leads)} leads from the database.")
    except Exception as e:
        print(f"Failed to fetch data from database: {e}")
        print("Please ensure your environment variables (.env) are properly configured with DB credentials.")
        return

    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    results = []

    for i, lead in enumerate(leads, 1):
        print(f"Processing lead {i}/{len(leads)} (Offer ID: {lead.get('offer_id')})...")
        processed = process_lead(lead, today_str)
        results.append(processed)

    output_file = "n8n_simulation_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
        
    print(f"Processing complete! N8N simulation results saved to {output_file}")


if __name__ == "__main__":
    main()

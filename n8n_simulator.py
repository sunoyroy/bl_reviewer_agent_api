import os
import json
import datetime
import requests
import psycopg2
import psycopg2.extras
import pandas as pd
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Remote n8n-style endpoint (same as Auditor HTTP Request node / psi deploy)
API_URL = os.getenv("API_URL", "https://bl-reviewer-agent-api-psi.vercel.app/review")

# local = call HybridBLReviewerAgent in-process (LLM fallback works with VPN/Groq .env)
# remote = POST to Vercel like Auditor (2).json (LLM may 403 if Intermesh blocks Vercel IPs)
REVIEW_MODE = os.getenv("REVIEW_MODE", "local").strip().lower()

# Database connection parameters
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "")

_LOCAL_AGENT = None


def _get_local_agent():
    """Build the same hybrid agent the API uses, so low title↔mcat similarity hits LLM."""
    global _LOCAL_AGENT
    if _LOCAL_AGENT is not None:
        return _LOCAL_AGENT

    from agent import build_bl_reviewer_agent

    api_key = os.getenv("LLM_GATEWAY_API_KEY")
    base_url = os.getenv("LLM_GATEWAY_BASE_URL", "https://imllm.intermesh.net/v1")
    model = os.getenv("LLM_GATEWAY_MODEL", "flex/openrouter/google/gemini-3-flash-preview")
    if not api_key:
        raise ValueError("REVIEW_MODE=local requires LLM_GATEWAY_API_KEY in .env")

    _LOCAL_AGENT = build_bl_reviewer_agent(model=model, api_key=api_key, base_url=base_url)
    print(f"Local agent ready | model={model} | base_url={base_url}")
    return _LOCAL_AGENT


def review_lead(payload: dict) -> dict:
    """Review one lead via local agent (default) or remote /review."""
    if REVIEW_MODE == "remote":
        response = requests.post(API_URL, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()

    from input_parser import parse_review_request

    agent = _get_local_agent()
    request = parse_review_request(payload)
    return agent.review(request)

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

def fetch_leads():
    # Calculate yesterday's date to match N8N logic
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"Fetching leads for date: {yesterday}")

    conn = get_db_connection()
    try:
        # 1. Determine which optional columns exist in the fact_pc_item table
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM im_dwh_rpt.fact_pc_item LIMIT 0")
            available_columns = {desc[0] for desc in cur.description}
            
        optional_fields = ['pc_item_desc_small', 'pc_item_img_original']
        
        # Build the dynamic select statements
        fpi_selects = []
        fo_selects = []
        for field in optional_fields:
            if field in available_columns:
                fpi_selects.append(f"fpi.{field}")
                fo_selects.append(f"fo.{field}")
            else:
                fpi_selects.append(f"'' AS {field}")
                fo_selects.append(f"fo.{field}")
                
        fpi_selects_sql = ",\n            ".join(fpi_selects)
        fo_selects_sql = ",\n        ".join(fo_selects)

        # 2. Build the main query
        query = f"""
        WITH filtered_offers AS (
            SELECT
                feo.eto_ofr_display_id,
                feo.eto_ofr_title,
                dgm.glcat_mcat_name,
                fpi.pc_item_display_id,
                fpi.pc_item_name,
                {fpi_selects_sql}
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
            ) AS isq_filled,
            fo.pc_item_display_id,
            fo.pc_item_name,
            {fo_selects_sql}
        FROM filtered_offers fo
        LEFT JOIN attribute_data ad
            ON fo.eto_ofr_display_id = ad.fk_eto_ofr_display_id
        GROUP BY
            fo.eto_ofr_display_id,
            fo.eto_ofr_title,
            fo.glcat_mcat_name,
            fo.pc_item_display_id,
            fo.pc_item_name,
            {fo_selects_sql}
        ORDER BY
            random()
        LIMIT 100;
        """

        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(query)
            rows = cur.fetchall()
            # Convert DictRow to standard dict
            return [dict(row) for row in rows]
    finally:
        conn.close()


def process_lead(lead, date_str):
    offer_id = str(lead.get('offer_id', ''))
    title = str(lead.get('title', ''))
    mcat = str(lead.get('mcat', ''))
    isq_filled_raw = str(lead.get('isq_filled', '{}'))
    
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
        api_result = review_lead(payload)
        reason = str(api_result.get("concise_reason", "") or "")
        if reason.startswith("BI Layer Approved"):
            path = "BI"
        elif "LLM fallback failed" in reason:
            path = "LLM_FAILED"
        else:
            path = "LLM"
        print(f"  -> {path} | flags={api_result.get('flags')} | conf={api_result.get('overall_confidence')}")
    except Exception as e:
        print(f"API request failed for offer_id {offer_id}: {e}")
        api_result = {
            "flags": [],
            "concise_reason": f"API Error: {str(e)}",
            "overall_confidence": None
        }

    # Map the output just like the N8N Google Sheets Node mapping
    # Column order matches the Google Sheets schema defined in Docs/Auditor (2).json
    return {
        "OfferID": offer_id,
        "Date": date_str,
        "Title": title,
        "MCAT": mcat,
        "ISQ": isq_filled_raw,
        "Flags": ", ".join(api_result.get("flags", [])),
        "reason": api_result.get("concise_reason", ""),
        "confidence": api_result.get("overall_confidence", None),
        "Display id product": str(lead.get('pc_item_display_id', '')),
        "pc_item_name": str(lead.get('pc_item_name', '')),
        "pc_item_desc_small": str(lead.get('pc_item_desc_small', '')),
        "pc_item_img_original": str(lead.get('pc_item_img_original', '')),
        "specs_json": isq_filled_raw
    }


def main():
    print(f"REVIEW_MODE={REVIEW_MODE}" + (f" | API_URL={API_URL}" if REVIEW_MODE == "remote" else " | using local HybridBLReviewerAgent"))
    try:
        leads = fetch_leads()
        print(f"Successfully fetched {len(leads)} leads from the database.")
    except Exception as e:
        print(f"Failed to fetch data from database: {e}")
        print("Please ensure your environment variables (.env) are properly configured with DB credentials.")
        return

    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    results = []
    path_counts = {"BI": 0, "LLM": 0, "LLM_FAILED": 0, "ERROR": 0}

    for i, lead in enumerate(leads, 1):
        print(f"Processing lead {i}/{len(leads)} (Offer ID: {lead.get('offer_id')})...")
        processed = process_lead(lead, today_str)
        results.append(processed)
        reason = str(processed.get("reason", "") or "")
        if reason.startswith("API Error"):
            path_counts["ERROR"] += 1
        elif reason.startswith("BI Layer Approved"):
            path_counts["BI"] += 1
        elif "LLM fallback failed" in reason:
            path_counts["LLM_FAILED"] += 1
        else:
            path_counts["LLM"] += 1

    output_json = "n8n_simulation_results.json"
    output_xlsx = "n8n_simulation_results.xlsx"
    
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
        
    # Enforce consistent column ordering matching the Google Sheets schema
    column_order = [
        "OfferID", "Date", "Title", "MCAT", "ISQ", "Flags", "reason",
        "confidence", "Display id product", "pc_item_name",
        "pc_item_desc_small", "pc_item_img_original", "specs_json"
    ]
    df = pd.DataFrame(results)
    # Reorder columns, adding any that might be missing with empty values
    for col in column_order:
        if col not in df.columns:
            df[col] = ''
    df = df[column_order]
    df.to_excel(output_xlsx, index=False)
        
    print(f"Processing complete! Results saved to {output_json} and {output_xlsx}")
    print(f"Path summary: BI={path_counts['BI']} LLM={path_counts['LLM']} LLM_FAILED={path_counts['LLM_FAILED']} ERROR={path_counts['ERROR']}")


if __name__ == "__main__":
    main()

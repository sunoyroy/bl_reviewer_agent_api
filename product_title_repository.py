"""Read the original product title associated with a buy-lead offer."""
from __future__ import annotations

import logging
import os

import psycopg2


LOGGER = logging.getLogger(__name__)


def fetch_original_product_title(offer_id: str) -> str:
    """Resolve fact_pc_item.pc_item_name from a buy-lead display ID.

    The query is parameterized and read-only. Any database/configuration failure
    is handled as a missing product title so Layer 2 cannot break review flow.
    """
    normalized_offer_id = str(offer_id or "").strip()
    if not normalized_offer_id:
        return ""

    required = ("DB_HOST", "DB_NAME", "DB_USER")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        LOGGER.warning(
            "Skipping product-title lookup for offer_id=%s; missing DB config: %s",
            normalized_offer_id,
            ", ".join(missing),
        )
        return ""

    connection = None
    try:
        connection = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT", "5432"),
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS", ""),
            connect_timeout=int(os.getenv("DB_CONNECT_TIMEOUT", "5")),
        )
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT fpi.pc_item_name
                FROM (
                    SELECT eto_ofr_modrefid, 1 AS source_priority
                    FROM im_dwh_rpt.fact_eto_ofr_live
                    WHERE eto_ofr_display_id = %s

                    UNION ALL

                    SELECT eto_ofr_modrefid, 2 AS source_priority
                    FROM im_dwh_rpt.fact_eto_ofr_expired
                    WHERE eto_ofr_display_id = %s
                ) AS offer
                JOIN im_dwh_rpt.fact_pc_item AS fpi
                    ON offer.eto_ofr_modrefid = fpi.pc_item_display_id
                WHERE TRIM(COALESCE(fpi.pc_item_name, '')) <> ''
                ORDER BY offer.source_priority
                LIMIT 1
                """,
                (normalized_offer_id, normalized_offer_id),
            )
            row = cursor.fetchone()
            return str(row[0]).strip() if row and row[0] else ""
    except Exception as exc:
        LOGGER.warning(
            "Product-title lookup failed for offer_id=%s: %s",
            normalized_offer_id,
            exc,
        )
        return ""
    finally:
        if connection is not None:
            connection.close()

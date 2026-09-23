from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterable
from typing import Any


def parse_review_request(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("PARAMS") or payload.get("vendor_json") or payload.get("response") or payload.get("data") or payload
    title = _first_present(
        raw,
        payload,
        ("title", "TITLE", "PRODUCT_NAME", "PRODUCT_TITLE", "AST_SELLER_TITLE", "eto_ofr_title"),
    )
    mcat = _first_present(
        raw,
        payload,
        ("mcat", "MCAT", "MCAT_NAME", "CATEGORY", "CATEGORY_NAME", "glcat_mcat_name"),
    )
    isq_filled = _first_present(
        raw,
        payload,
        ("isq_filled", "ISQ_FILLED", "ISQ_DATA", "attributes_combined"),
    ) or {}
    isq_asked = _first_present(
        raw,
        payload,
        ("isq_asked", "ISQ_ASKED", "ISQ_QUESTIONS", "QUESTIONS_ASKED", "ASKED_ISQ"),
    ) or {}

    parsed_isq_filled = coerce_isq_map(isq_filled)
    parsed_isq_asked = coerce_isq_map(isq_asked) if isq_asked else {field: field for field in parsed_isq_filled}

    return {
        "title": str(title or ""),
        "mcat": str(mcat or ""),
        "isq_filled": parsed_isq_filled,
        "isq_asked": parsed_isq_asked,
        "metadata": {
            key: value
            for key, value in {
                "input_shape": "squadstack_envelope" if "PARAMS" in payload else "review_request",
                "offer_id": _first_present(
                    raw,
                    payload,
                    ("OFFER_ID", "offer_id", "eto_ofr_display_id", "ETO_OFR_DISPLAY_ID"),
                )
                if isinstance(raw, dict)
                else None,
            }.items()
            if value not in (None, "", [], {})
        },
    }


def csv_row_to_lead(row: dict[str, str]) -> dict[str, Any]:
    isq_filled = parse_attribute_pairs(row.get("attributes_combined", ""))
    return {
        "offer_id": row.get("eto_ofr_display_id", ""),
        "title": row.get("eto_ofr_title", ""),
        "mcat": row.get("glcat_mcat_name", ""),
        "isq_filled": isq_filled,
        "isq_asked": list(isq_filled.keys()),
    }


def coerce_isq_map(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return {_canonical_key(key): item for key, item in value.items() if _canonical_key(key)}
    if isinstance(value, str):
        parsed = _parse_isq_data(value)
        if parsed:
            return coerce_isq_map(parsed)
        parsed_list = _parse_list_string(value)
        if parsed_list is not None:
            return coerce_isq_map(parsed_list)
        parsed_attributes = parse_attribute_pairs(value)
        if parsed_attributes:
            return coerce_isq_map(parsed_attributes)
        key = _canonical_key(value)
        return {key: value} if key else {}
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        result: dict[str, Any] = {}
        for item in value:
            if isinstance(item, dict):
                key = item.get("field") or item.get("name") or item.get("key") or item.get("question")
                question = item.get("question") or item.get("label") or item.get("value") or key
            else:
                key = item
                question = item
            canonical = _canonical_key(key)
            if canonical:
                result[canonical] = question
        return result
    return {}


def parse_attribute_pairs(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    if not value or ":" not in value:
        return result

    for part in value.split(";"):
        text = part.strip()
        if not text:
            continue
        if ":" in text:
            key, item = text.split(":", 1)
        else:
            key, item = text, ""
        key = key.strip()
        item = item.strip()
        if not key:
            continue
        deduped_key = key
        index = 2
        while deduped_key in result:
            deduped_key = f"{key} #{index}"
            index += 1
        result[deduped_key] = item
    return result


def _parse_isq_data(raw_value: Any) -> dict[str, Any]:
    if isinstance(raw_value, dict):
        return raw_value
    if not isinstance(raw_value, str) or not raw_value.strip():
        return {}

    try:
        parsed = ast.literal_eval(raw_value)
    except (SyntaxError, ValueError):
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_list_string(value: str) -> Any | None:
    text = value.strip()
    if not text:
        return None
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(text)
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue
        if isinstance(parsed, list):
            return parsed
    return None


def _canonical_key(key: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", str(key).upper()).strip("_")


def _first_present(primary: dict[str, Any], secondary: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for source in (primary, secondary):
        if not isinstance(source, dict):
            continue
        for key in keys:
            if source.get(key) not in (None, ""):
                return source[key]
    return None

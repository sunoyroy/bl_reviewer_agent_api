from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any
# from .input_parser import csv_row_to_lead
from .input_parser import csv_row_to_lead, parse_review_request
from .prompt import BATCH_SYSTEM_PROMPT


DEFAULT_MODEL = "google/gemini-3-flash-preview"
DEFAULT_BASE_URL = "https://imllm.intermesh.net/v1"


def parse_args() -> argparse.Namespace:
    # parser = argparse.ArgumentParser(description="Run BL reviewer over a CSV through an LLM gateway.")
    # parser.add_argument("--input", required=True, type=Path, help="Input CSV path.")
    parser = argparse.ArgumentParser(description="Run BL reviewer over a JSON/CSV through an LLM gateway.")
    parser.add_argument("--input", type=Path, help="Input CSV or JSON path.")
    parser.add_argument("--json", help="One JSON payload as a string.")
    parser.add_argument("--output-dir", default=Path("outputs") / "bl_reviewer_agent_batch", type=Path)
    parser.add_argument("--base-url", default=os.getenv("LLM_GATEWAY_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--models", nargs="+", default=[os.getenv("LLM_GATEWAY_MODEL", DEFAULT_MODEL)])
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--sleep", type=float, default=0.5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.getenv("LLM_GATEWAY_API_KEY")
    if not api_key:
        print("Missing LLM_GATEWAY_API_KEY.", file=sys.stderr)
        return 2

    # Check if we should process the input as a JSON payload or fall back to CSV.
    # We treat it as JSON if --json is provided, the input file suffix is not .csv, or data is piped via stdin.
    is_json = False
    if args.json:
        is_json = True
    elif args.input:
        is_json = args.input.suffix.lower() != ".csv"
    elif not sys.stdin.isatty():
        is_json = True
    else:
        print("Error: Provide input using --input, --json, or stdin.", file=sys.stderr)
        return 2

    if is_json:
        # Load the raw payload from the appropriate source: --json string, --input JSON file, or stdin pipe
        raw_payload = None
        if args.json:
            raw_payload = json.loads(args.json)
        elif args.input:
            raw_payload = json.loads(args.input.read_text(encoding="utf-8"))
        elif not sys.stdin.isatty():
            raw = sys.stdin.read().strip()
            if raw:
                raw_payload = json.loads(raw)

        if raw_payload is None:
            print("Error: Empty JSON input.", file=sys.stderr)
            return 2

        # Extract list of leads from raw JSON: can be a direct list, wrapped in {"leads": [...]}, or a single lead dict
        if isinstance(raw_payload, list):
            parsed_leads = raw_payload
        elif isinstance(raw_payload, dict):
            if "leads" in raw_payload and isinstance(raw_payload["leads"], list):
                parsed_leads = raw_payload["leads"]
            else:
                parsed_leads = [raw_payload]
        else:
            print("Error: Invalid JSON format.", file=sys.stderr)
            return 2

        leads = []
        rows = []
        for item in parsed_leads:
            # Parse the lead into standard review request format
            lead = parse_review_request(item)
            # Ensure the unique offer_id identifier is promoted to the root level
            if "offer_id" not in lead and "metadata" in lead and "offer_id" in lead["metadata"]:
                lead["offer_id"] = lead["metadata"]["offer_id"]
            leads.append(lead)

            # Reconstruct mock row mimicking CSV columns to remain compatible with CSV writers downstream
            row = {
                "eto_ofr_display_id": str(lead.get("offer_id") or ""),
                "eto_ofr_title": lead.get("title", ""),
                "glcat_mcat_name": lead.get("mcat", ""),
                "attributes_combined": "; ".join(f"{k}: {v}" for k, v in lead.get("isq_filled", {}).items()),
            }
            rows.append(row)
    else:
        # Standard legacy fallback to read directly from a CSV file
        rows = read_csv(args.input)
        if args.limit:
            rows = rows[: args.limit]
        leads = [csv_row_to_lead(row) for row in rows]
    args.output_dir.mkdir(parents=True, exist_ok=True)

    all_model_results: dict[str, dict[str, dict[str, Any]]] = {}
    for model in args.models:
        print(f"Running {model} on {len(leads)} leads...")
        json_path = args.output_dir / f"{safe_name(model)}_results.json"
        csv_path = args.output_dir / f"{safe_name(model)}_results.csv"
        existing = read_existing_results(json_path)
        results = run_model(
            model=model,
            leads=leads,
            rows=rows,
            api_key=api_key,
            base_url=args.base_url,
            batch_size=max(1, args.batch_size),
            sleep_seconds=max(0.0, args.sleep),
            existing_results=existing,
            checkpoint_json_path=json_path,
            checkpoint_csv_path=csv_path,
        )
        all_model_results[model] = {str(item.get("offer_id")): item for item in results}
        write_json(json_path, results)
        write_model_csv(csv_path, rows, results)

    combined_path = args.output_dir / "combined_model_results.csv"
    write_combined_csv(combined_path, rows, all_model_results)
    summary = build_summary(all_model_results)
    write_json(args.output_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    print(f"Combined CSV: {combined_path}")
    return 0


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def run_model(
    *,
    model: str,
    leads: list[dict[str, Any]],
    rows: list[dict[str, str]],
    api_key: str,
    base_url: str,
    batch_size: int,
    sleep_seconds: float,
    existing_results: list[dict[str, Any]],
    checkpoint_json_path: Path,
    checkpoint_csv_path: Path,
) -> list[dict[str, Any]]:
    completed = {str(item.get("offer_id")): item for item in existing_results if item.get("offer_id")}
    missing = [lead for lead in leads if str(lead.get("offer_id", "")) not in completed]
    if completed:
        print(f"  resuming with {len(completed)} completed, {len(missing)} remaining")

    for start in range(0, len(missing), batch_size):
        batch = missing[start : start + batch_size]
        print(f"  batch {start + 1}-{start + len(batch)} of {len(missing)} remaining")
        for item in call_batch_with_recovery(model, batch, api_key, base_url):
            completed[str(item.get("offer_id"))] = item
        checkpoint = ordered_results(leads, completed)
        write_json(checkpoint_json_path, checkpoint)
        write_model_csv(checkpoint_csv_path, rows, checkpoint)
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return ordered_results(leads, completed)


def read_existing_results(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict) and not is_gateway_error_result(item)]


def ordered_results(leads: list[dict[str, Any]], by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [by_id[str(lead.get("offer_id", ""))] for lead in leads if str(lead.get("offer_id", "")) in by_id]


def is_gateway_error_result(item: dict[str, Any]) -> bool:
    flags = item.get("flags", [])
    if not isinstance(flags, list):
        return False
    return False


def call_batch_with_recovery(
    model: str,
    batch: list[dict[str, Any]],
    api_key: str,
    base_url: str,
) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            return call_batch(model, batch, api_key, base_url)
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 * (attempt + 1))

    exc = last_error or RuntimeError("Unknown gateway error.")
    if len(batch) == 1:
        lead = batch[0]
        return [
            {
                "offer_id": lead.get("offer_id", ""),
                "flags": [],
                "concise_reason": f"Gateway call failed: {str(exc)[:100]}",
            }
        ]

    midpoint = len(batch) // 2
    return call_batch_with_recovery(model, batch[:midpoint], api_key, base_url) + call_batch_with_recovery(
        model,
        batch[midpoint:],
        api_key,
        base_url,
    )


def call_batch(model: str, batch: list[dict[str, Any]], api_key: str, base_url: str) -> list[dict[str, Any]]:
    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": BATCH_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Review these buy leads and return only the JSON object.\n"
                + json.dumps({"leads": batch}, ensure_ascii=True),
            },
        ],
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {details}") from exc

    parsed = extract_json(payload["choices"][0]["message"]["content"])
    results = parsed.get("results")
    if not isinstance(results, list):
        raise ValueError("Model response missing results list.")
    by_id = {str(item.get("offer_id")): item for item in results if isinstance(item, dict)}
    return [normalize_result(by_id.get(str(lead.get("offer_id")), missing_result(lead))) for lead in batch]


def missing_result(lead: dict[str, Any]) -> dict[str, Any]:
    return {
        "offer_id": str(lead.get("offer_id", "")),
        "flags": [],
        "concise_reason": "Missing from model response.",
    }


def extract_json(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])


VALID_FLAG_NAMES: frozenset[str] = frozenset({
    "title_mcat_mismatch",
    "isq_filled_title_mismatch",
    "isq_filled_mcat_mismatch",
})


def normalize_result(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize a model result. Flags are already string names per the prompt contract."""
    raw_flags = item.get("flags")
    if not isinstance(raw_flags, list):
        raw_flags = []

    # Accept only valid known string flag names
    flag_names: list[str] = [str(f) for f in raw_flags if isinstance(f, str) and str(f) in VALID_FLAG_NAMES]

    return {
        "offer_id": str(item.get("offer_id", "")),
        "flags": flag_names,
        "concise_reason": str(item.get("concise_reason", "")),
    }


def to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def write_model_csv(path: Path, rows: list[dict[str, str]], model_results: list[dict[str, Any]]) -> None:
    by_id = {str(item.get("offer_id")): item for item in model_results}
    fieldnames = list(rows[0].keys()) if rows else []
    extra = ["status", "overall_confidence", "flag_count", "flag_types", "flag_reasons", "concise_reason", "flags_json"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames + extra)
        writer.writeheader()
        for row in rows:
            result = by_id.get(str(row.get("eto_ofr_display_id", "")), {})
            writer.writerow({**row, **result_to_flat(result)})


def write_combined_csv(path: Path, rows: list[dict[str, str]], all_results: dict[str, dict[str, dict[str, Any]]]) -> None:
    fieldnames = list(rows[0].keys()) if rows else []
    model_fields: list[str] = []
    for model in all_results:
        prefix = safe_name(model)
        model_fields.extend(
            [
                f"{prefix}_status",
                f"{prefix}_overall_confidence",
                f"{prefix}_flag_count",
                f"{prefix}_flag_types",
                f"{prefix}_flag_reasons",
                f"{prefix}_concise_reason",
                f"{prefix}_flags_json",
            ]
        )

    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames + model_fields)
        writer.writeheader()
        for row in rows:
            offer_id = str(row.get("eto_ofr_display_id", ""))
            output = dict(row)
            for model, by_id in all_results.items():
                prefix = safe_name(model)
                flat = result_to_flat(by_id.get(offer_id, {}))
                for key, value in flat.items():
                    output[f"{prefix}_{key}"] = value
            writer.writerow(output)


def result_to_flat(result: dict[str, Any]) -> dict[str, Any]:
    flags = result.get("flags", [])
    if not isinstance(flags, list):
        flags = []

    # flags are already resolved to string names by normalize_result
    flag_types_list = [str(f) for f in flags]

    status = "approved" if not flags else "needs_review"
    overall_confidence = result.get("overall_confidence")
    if overall_confidence is None:
        overall_confidence = 1.0 if not flags else 0.5

    return {
        "status": status,
        "overall_confidence": overall_confidence,
        "flag_count": len(flags),
        "flag_types": "; ".join(flag_types_list),
        "flag_reasons": result.get("concise_reason", "") if flags else "",
        "concise_reason": result.get("concise_reason", ""),
        "flags_json": json.dumps(flags, ensure_ascii=True),
    }


def build_summary(all_results: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for model, by_id in all_results.items():
        statuses = Counter()
        flag_types: Counter = Counter()
        total_flags = 0
        confidence_sum = 0.0

        for result in by_id.values():
            flags = result.get("flags", [])
            status = "approved" if not flags else "needs_review"
            statuses[status] += 1

            overall_confidence = result.get("overall_confidence")
            if overall_confidence is None:
                overall_confidence = 1.0 if not flags else 0.5
            confidence_sum += to_float(overall_confidence, 1.0)

            if isinstance(flags, list):
                total_flags += len(flags)
                # flags are already resolved string names
                for flag in flags:
                    flag_types[str(flag)] += 1

        count = len(by_id)
        summary[model] = {
            "rows": count,
            "statuses": dict(statuses),
            "average_confidence": round(confidence_sum / count, 4) if count else 0.0,
            "total_flags": total_flags,
            "top_flag_types": dict(flag_types.most_common(20)),
        }
    return summary


def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()


if __name__ == "__main__":
    raise SystemExit(main())

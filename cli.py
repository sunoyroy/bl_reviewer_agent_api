from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .agent import build_bl_reviewer_agent
from .input_parser import parse_review_request


DEFAULT_MODEL = "flex/openrouter/google/gemini-3-flash-preview"
DEFAULT_BASE_URL = "https://imllm.intermesh.net/v1"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review one buy lead through an OpenAI-compatible LLM gateway.")
    parser.add_argument("--input", "-i", type=Path, help="Path to one JSON payload.")
    parser.add_argument("--json", help="One JSON payload as a string.")
    parser.add_argument("--output", "-o", type=Path, help="Optional path to write the review JSON.")
    parser.add_argument("--model", default=os.getenv("LLM_GATEWAY_MODEL", DEFAULT_MODEL))
    parser.add_argument("--base-url", default=os.getenv("LLM_GATEWAY_BASE_URL", DEFAULT_BASE_URL))
    return parser.parse_args(argv)


def load_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.json:
        return json.loads(args.json)
    if args.input:
        return json.loads(args.input.read_text(encoding="utf-8"))
    if not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
        if raw:
            return json.loads(raw)
    raise ValueError("Provide a JSON payload using --input, --json, or stdin.")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    api_key = os.getenv("LLM_GATEWAY_API_KEY")
    
    if not api_key:
        print("Error: Missing LLM_GATEWAY_API_KEY environment variable. Local processing is no longer supported.", file=sys.stderr)
        return 2

    try:
        payload = load_payload(args)
        request = parse_review_request(payload)
        agent = build_bl_reviewer_agent(
            model=args.model,
            api_key=api_key,
            base_url=args.base_url,
        )
        report = agent.review(request)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(report, indent=2, ensure_ascii=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
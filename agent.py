from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

try:
    from .prompt import BATCH_SYSTEM_PROMPT, build_reviewer_prompt
except ImportError:  # pragma: no cover - supports Vercel top-level module import
    from prompt import BATCH_SYSTEM_PROMPT, build_reviewer_prompt


def _normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _tokenize(text: str) -> set[str]:
    stopwords = {
        "a",
        "an",
        "and",
        "for",
        "of",
        "the",
        "to",
        "with",
        "in",
        "on",
        "is",
        "are",
        "be",
        "it",
        "this",
        "that",
        "these",
        "those",
        "from",
        "or",
    }
    return {
        token
        for token in _normalize_text(text).split()
        if token and token not in stopwords
    }


class LocalBLReviewerAgent:
    def __init__(self, model: str, base_url: str | None = None) -> None:
        self.model = model
        self.base_url = (base_url or "").rstrip("/")

    def review(self, request: dict[str, Any]) -> dict[str, Any]:
        offer_id = str(request.get("offer_id") or request.get("metadata", {}).get("offer_id") or "")
        title = str(request.get("title") or request.get("metadata", {}).get("title") or "")
        mcat = str(request.get("mcat") or request.get("metadata", {}).get("mcat") or "")

        flags: list[str] = []
        concise_reason = "Title and mcat are consistent."

        if title and mcat:
            title_tokens = _tokenize(title)
            mcat_tokens = _tokenize(mcat)
            if title_tokens and mcat_tokens and not (title_tokens & mcat_tokens):
                flags.append("title_mcat_mismatch")
                concise_reason = "Title and mcat appear inconsistent."
            elif _normalize_text(title) != _normalize_text(mcat):
                if " " in title and " " in mcat:
                    shared_tokens = title_tokens & mcat_tokens
                    if not shared_tokens:
                        flags.append("title_mcat_mismatch")
                        concise_reason = "Title and mcat appear inconsistent."

        return {
            "offer_id": offer_id,
            "flags": flags,
            "concise_reason": concise_reason,
        }


class OpenAICompatibleBLReviewerAgent:
    def __init__(self, model: str, api_key: str, base_url: str) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def review(self, request: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": BATCH_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_reviewer_prompt(request),
                },
            ],
        }
        http_request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(http_request, timeout=180) as response:
                raw_response = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM gateway request failed with HTTP {exc.code}: {detail}") from exc

        content = raw_response["choices"][0]["message"]["content"]
        report = extract_json_object(content)

        # Model returns flag names directly as strings per the prompt contract
        raw_flags = report.get("flags") or []
        flags: list[str] = [str(f) for f in raw_flags if isinstance(f, str)]

        return {
            "offer_id": str(report.get("offer_id") or request.get("metadata", {}).get("offer_id") or ""),
            "flags": flags,
            "concise_reason": str(report.get("concise_reason") or ""),
        }


def build_bl_reviewer_agent(
    *,
    model: str,
    api_key: str | None,
    base_url: str | None,
) -> OpenAICompatibleBLReviewerAgent | LocalBLReviewerAgent:
    if not api_key:
        return LocalBLReviewerAgent(model=model, base_url=base_url)
    if not base_url:
        raise ValueError("LLM base URL is required. Set LLM_GATEWAY_BASE_URL.")
    return OpenAICompatibleBLReviewerAgent(model=model, api_key=api_key, base_url=base_url)


def extract_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("LLM response must be a JSON object.")
    return parsed

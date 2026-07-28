from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

os.environ["HF_HOME"] = "/tmp/hf_cache"
os.environ["FASTEMBED_CACHE_PATH"] = "/tmp/fastembed_cache"
os.environ["TRANSFORMERS_CACHE"] = "/tmp/transformers_cache"
os.environ["NUMEXPR_MAX_THREADS"] = "1"

BI_AVAILABLE = False
try:
    import numpy as np
    from fastembed import TextEmbedding
    BI_AVAILABLE = True
except ImportError:
    np = None
    TextEmbedding = None

try:
    from .prompt import BATCH_SYSTEM_PROMPT, build_reviewer_prompt
except ImportError:
    from prompt import BATCH_SYSTEM_PROMPT, build_reviewer_prompt


class LocalEmbeddingEngine:
    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self.model = TextEmbedding(
            model_name=model_name,
            cache_dir="/tmp/fastembed_cache",
            threads=1,
        )

    def calculate_similarity(self, text1: str, text2: str) -> float:
        text1 = text1.strip()
        text2 = text2.strip()

        if not text1 or not text2:
            return 0.0

        embeddings = list(self.model.embed([text1, text2]))
        if len(embeddings) != 2:
            return 0.0

        e1, e2 = embeddings
        denom = np.linalg.norm(e1) * np.linalg.norm(e2)

        if denom == 0:
            return 0.0

        return float(np.dot(e1, e2) / denom)


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
                {"role": "user", "content": build_reviewer_prompt(request)},
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
            with urllib.request.urlopen(http_request, timeout=60) as response:
                raw_response = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"LLM gateway request failed with HTTP {exc.code}: {detail}"
            ) from exc

        content = raw_response["choices"][0]["message"]["content"]
        report = extract_json_object(content)

        flags = [
            str(f)
            for f in (report.get("flags") or [])
            if isinstance(f, str)
        ]

        return {
            "offer_id": str(
                report.get("offer_id")
                or request.get("metadata", {}).get("offer_id")
                or request.get("offer_id")
                or ""
            ),
            "flags": flags,
            "concise_reason": str(report.get("concise_reason") or ""),
            "overall_confidence": float(report.get("overall_confidence", 0.0)),
        }


class HybridBLReviewerAgent:
    def __init__(
        self,
        llm_agent: OpenAICompatibleBLReviewerAgent,
        threshold: float = 0.60,
    ) -> None:
        self.llm_agent = llm_agent
        self.threshold = threshold
        self.bi_engine = None

        if BI_AVAILABLE:
            try:
                self.bi_engine = LocalEmbeddingEngine()
                print("Semantic BI engine initialized.")
            except Exception as e:
                print(f"BI initialization skipped: {e}")
                self.bi_engine = None

    def review(self, request: dict[str, Any]) -> dict[str, Any]:
        offer_id = str(
            request.get("offer_id")
            or request.get("metadata", {}).get("offer_id")
            or ""
        )

        title = str(request.get("title") or "")
        mcat = str(request.get("mcat") or "")

        similarity = 0.0

        if self.bi_engine:
            try:
                similarity = self.bi_engine.calculate_similarity(title, mcat)
            except Exception as e:
                print(f"Semantic similarity failed: {e}")
                similarity = 0.0

        if similarity >= self.threshold:
            return {
                "offer_id": offer_id,
                "flags": [],
                "concise_reason": "BI Layer Approved: High semantic similarity match.",
                "overall_confidence": round(similarity, 2),
            }

        try:
            llm_response = self.llm_agent.review(request)
            llm_response["overall_confidence"] = round(similarity, 2)
            return llm_response

        except Exception as e:
            return {
                "offer_id": offer_id,
                "flags": ["title_mcat_mismatch"],
                "concise_reason": f"System Error: LLM fallback failed: {e}",
                "overall_confidence": round(similarity, 2),
            }


def build_bl_reviewer_agent(
    *,
    model: str,
    api_key: str | None,
    base_url: str | None,
    nlp_threshold: float = 0.60,
) -> HybridBLReviewerAgent:
    if not api_key:
        raise ValueError("API key is required.")
    if not base_url:
        raise ValueError("LLM base URL is required.")

    llm_agent = OpenAICompatibleBLReviewerAgent(
        model=model,
        api_key=api_key,
        base_url=base_url,
    )

    return HybridBLReviewerAgent(
        llm_agent=llm_agent,
        threshold=nlp_threshold,
    )


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
        parsed = json.loads(text[start:end + 1])

    if not isinstance(parsed, dict):
        raise ValueError("LLM response must be a JSON object.")

    return parsed

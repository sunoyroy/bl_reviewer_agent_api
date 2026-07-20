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

try:
    from sentence_transformers import SentenceTransformer, util
except ImportError:  # pragma: no cover - keeps the module usable without the optional dependency
    SentenceTransformer = None
    util = None


class LocalEmbeddingEngine:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model = SentenceTransformer(model_name) if SentenceTransformer is not None else None

    def calculate_similarity(self, text1: str, text2: str) -> float:
        if not text1.strip() or not text2.strip():
            return 0.0

        if self.model is None or util is None:
            return self._fallback_similarity(text1, text2)

        embedding1 = self.model.encode(text1, convert_to_tensor=True)
        embedding2 = self.model.encode(text2, convert_to_tensor=True)
        similarity = util.cos_sim(embedding1, embedding2)
        return float(similarity.item())

    def _fallback_similarity(self, text1: str, text2: str) -> float:
        tokens1 = set(re.findall(r"[a-z0-9]+", text1.lower()))
        tokens2 = set(re.findall(r"[a-z0-9]+", text2.lower()))
        if not tokens1 or not tokens2:
            return 0.0
        union = tokens1 | tokens2
        if not union:
            return 0.0
        return len(tokens1 & tokens2) / len(union)


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

        raw_flags = report.get("flags") or []
        flags: list[str] = [str(f) for f in raw_flags if isinstance(f, str)]

        return {
            "offer_id": str(report.get("offer_id") or request.get("metadata", {}).get("offer_id") or request.get("offer_id") or ""),
            "flags": flags,
            "concise_reason": str(report.get("concise_reason") or ""),
        }


class HybridBLReviewerAgent:
    def __init__(self, llm_agent: OpenAICompatibleBLReviewerAgent, threshold: float = 0.45) -> None:
        self.llm_agent = llm_agent
        self.threshold = threshold
        self.bi_engine = LocalEmbeddingEngine()

    def review(self, request: dict[str, Any]) -> dict[str, Any]:
        offer_id = str(request.get("offer_id") or request.get("metadata", {}).get("offer_id") or "")
        title = str(request.get("title") or "")
        mcat = str(request.get("mcat") or "")

        similarity = self.bi_engine.calculate_similarity(title, mcat)

        if similarity >= self.threshold:
            return {
                "offer_id": offer_id,
                "flags": [],
                "concise_reason": f"BI Layer: High semantic similarity match ({similarity:.2f}).",
            }

        try:
            return self.llm_agent.review(request)
        except Exception as exc:
            return {
                "offer_id": offer_id,
                "flags": ["title_mcat_mismatch"],
                "concise_reason": f"BI Layer: Cosine similarity low ({similarity:.2f}). LLM fallback failed: {exc}",
            }


def build_bl_reviewer_agent(
    *,
    model: str,
    api_key: str | None,
    base_url: str | None,
    nlp_threshold: float = 0.45,
) -> HybridBLReviewerAgent:
    if not api_key or not base_url:
        llm_agent = OpenAICompatibleBLReviewerAgent(model=model, api_key=api_key or "", base_url=base_url or "https://example.invalid")
        return HybridBLReviewerAgent(llm_agent=llm_agent, threshold=nlp_threshold)

    llm_agent = OpenAICompatibleBLReviewerAgent(model=model, api_key=api_key, base_url=base_url)
    return HybridBLReviewerAgent(llm_agent=llm_agent, threshold=nlp_threshold)


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
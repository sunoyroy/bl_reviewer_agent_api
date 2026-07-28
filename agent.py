from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

# ==============================================================================
# CRITICAL VERCEL FIX: Force all AI caching to the writable /tmp directory
# ==============================================================================
os.environ["HF_HOME"] = "/tmp/hf_cache"
os.environ["FASTEMBED_CACHE_PATH"] = "/tmp/fastembed_cache"
os.environ["TRANSFORMERS_CACHE"] = "/tmp/transformers_cache"
os.environ["NUMEXPR_MAX_THREADS"] = "1"

try:
    import numpy as np
    from fastembed import TextEmbedding
except ImportError:
    raise ImportError("Please ensure 'fastembed' and 'numpy' are added to your requirements.txt")

try:
    from .prompt import BATCH_SYSTEM_PROMPT, build_reviewer_prompt
except ImportError:  # pragma: no cover
    from prompt import BATCH_SYSTEM_PROMPT, build_reviewer_prompt


class LocalEmbeddingEngine:
    def __init__(self, model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"):
        # Use the alias identifier for FastEmbed, pointing to /tmp
        self.model = TextEmbedding(model_name=model_name, cache_dir="/tmp/fastembed_cache")

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Computes true semantic cosine similarity."""
        if not text1.strip() or not text2.strip():
            return 0.0
            
        embeddings = list(self.model.embed([text1, text2]))
        if len(embeddings) < 2: return 0.0
        
        e1, e2 = embeddings[0], embeddings[1]
        dot_product = np.dot(e1, e2)
        norm_a = np.linalg.norm(e1)
        norm_b = np.linalg.norm(e2)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
            
        return float(dot_product / (norm_a * norm_b))


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
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(http_request, timeout=180) as response:
            raw_response = json.loads(response.read().decode("utf-8"))

        content = raw_response["choices"][0]["message"]["content"]
        report = extract_json_object(content)

        return {
            "offer_id": str(report.get("offer_id") or request.get("metadata", {}).get("offer_id") or request.get("offer_id") or ""),
            "flags": [str(f) for f in (report.get("flags") or []) if isinstance(f, str)],
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

        # Compute semantic similarity locally
        similarity = self.bi_engine.calculate_similarity(title, mcat)
        sim_val = round(float(similarity), 2)

        if similarity >= self.threshold:
            return {
                "offer_id": offer_id,
                "flags": [],
                "concise_reason": f"BI Layer Approved: High semantic similarity match ({sim_val}).",
                "overall_confidence": sim_val
            }
        else:
            try:
                res = self.llm_agent.review(request)
                res["overall_confidence"] = sim_val
                return res
            except Exception as e:
                return {
                    "offer_id": offer_id,
                    "flags": ["title_mcat_mismatch"],
                    "concise_reason": f"BI Layer Mismatch: Cosine similarity low ({sim_val}). LLM fallback failed: {e}",
                    "overall_confidence": sim_val
                }


def build_bl_reviewer_agent(*, model: str, api_key: str | None, base_url: str | None, nlp_threshold: float = 0.60) -> HybridBLReviewerAgent:
    if not api_key or not base_url:
        raise ValueError("API key and base URL are required.")
    return HybridBLReviewerAgent(
        llm_agent=OpenAICompatibleBLReviewerAgent(model=model, api_key=api_key, base_url=base_url),
        threshold=nlp_threshold
    )


def extract_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("LLM response must be a JSON object.")
    return parsed

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

# ==============================================================================
# CRITICAL VERCEL FIX: Force all AI caching to the writable /tmp directory
# These MUST be set before importing fastembed or numpy.
# ==============================================================================
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
    pass

try:
    from .prompt import BATCH_SYSTEM_PROMPT, build_reviewer_prompt
except ImportError:  # pragma: no cover
    from prompt import BATCH_SYSTEM_PROMPT, build_reviewer_prompt


class LocalEmbeddingEngine:
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        # Explicitly point the FastEmbed engine to /tmp and restrict threading.
        # threads=1 is CRITICAL for Vercel to prevent OS Error 30 during freeze/thaw.
        self.model = TextEmbedding(model_name=model_name, cache_dir="/tmp/fastembed_cache", threads=1)

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Computes true semantic cosine similarity using fast local ONNX vectors."""
        if not text1.strip() or not text2.strip():
            return 0.0
            
        embeddings = list(self.model.embed([text1, text2]))
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
    def __init__(self, llm_agent: OpenAICompatibleBLReviewerAgent, threshold: float = 0.60) -> None:
        self.llm_agent = llm_agent
        self.threshold = threshold
        self.bi_engine = None
        
        # Graceful Initialization: If Vercel blocks the model, don't crash the whole app.
        if BI_AVAILABLE:
            try:
                self.bi_engine = LocalEmbeddingEngine()
            except Exception as e:
                print(f"BI Initialization skipped due to environment limits: {e}")

    def review(self, request: dict[str, Any]) -> dict[str, Any]:
        offer_id = str(request.get("offer_id") or request.get("metadata", {}).get("offer_id") or "")
        
        # If BI failed to load, route directly to LLM to guarantee n8n gets a response
        if not self.bi_engine:
            return self.llm_agent.review(request)

        title = str(request.get("title") or "")
        mcat = str(request.get("mcat") or "")

        try:
            # Compute semantic similarity locally on Vercel using FastEmbed
            similarity = self.bi_engine.calculate_similarity(title, mcat)

            if similarity >= self.threshold:
                return {
                    "offer_id": offer_id,
                    "flags": [],
                    "concise_reason": f"BI Layer Approved: High semantic similarity match ({similarity:.2f})."
                }
        except Exception:
            pass # Fallthrough to LLM on BI failure

        # If similarity is low, or the BI math crashed, fallback to LLM
        try:
            return self.llm_agent.review(request)
        except Exception as e:
            return {
                "offer_id": offer_id,
                "flags": ["title_mcat_mismatch"],
                "concise_reason": f"BI Layer Mismatch: Cosine similarity low. LLM fallback failed: {e}",
            }


def build_bl_reviewer_agent(
    *,
    model: str,
    api_key: str | None,
    base_url: str | None,
    nlp_threshold: float = 0.60
) -> HybridBLReviewerAgent:
    if not api_key:
        raise ValueError("API key is required.")
    if not base_url:
        raise ValueError("LLM base URL is required. Set LLM_GATEWAY_BASE_URL.")
    
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
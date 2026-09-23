from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable
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
    from .product_title_repository import fetch_original_product_title
except ImportError:  # pragma: no cover
    from prompt import BATCH_SYSTEM_PROMPT, build_reviewer_prompt
    from product_title_repository import fetch_original_product_title


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
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "bl-reviewer-agent/1.0",
            },
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
    def __init__(
        self,
        llm_agent: OpenAICompatibleBLReviewerAgent,
        threshold: float = 0.60,
        layer2_enabled: bool | None = None,
        product_title_resolver: Callable[[str], str] | None = None,
    ) -> None:
        self.llm_agent = llm_agent
        self.threshold = threshold
        self.bi_engine = LocalEmbeddingEngine()
        self.product_title_resolver = product_title_resolver or fetch_original_product_title
        if layer2_enabled is None:
            layer2_enabled = os.getenv("LAYER2_ENABLED", "true").strip().lower() not in {
                "0",
                "false",
                "no",
                "off",
            }
        self.layer2_enabled = layer2_enabled

    def _resolve_original_product_title(self, offer_id: str) -> str:
        """Fetch the original product title internally; never trust request data."""
        try:
            return str(self.product_title_resolver(offer_id) or "").strip()
        except Exception:
            return ""

    def _layer2_validate(
        self,
        *,
        offer_id: str,
        original_title: str,
        mcat: str,
        layer1_sim: float,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """Independently validate Original Product Title vs MCAT after Layer 1 BI approve."""
        try:
            similarity = self.bi_engine.calculate_similarity(original_title, mcat)
            sim2 = round(float(similarity), 2)
            # High Layer2: confirm approve only when original-product vs MCAT > threshold
            if sim2 > self.threshold:
                return {
                    "offer_id": offer_id,
                    "flags": [],
                    "concise_reason": (
                        f"BI+Layer2 Approved: BL-MCAT ({layer1_sim}) and "
                        f"original-product-MCAT ({sim2}) both match."
                    ),
                    "overall_confidence": layer1_sim,
                    "layer2_triggered": True,
                    "layer2_similarity": sim2,
                    "layer2_result": "match",
                }

            # Low Layer2: escalate to LLM (judge original product title vs MCAT / ISQ)
            try:
                layer2_request = dict(request)
                layer2_request["title"] = original_title
                layer2_request["original_product_title"] = original_title
                res = self.llm_agent.review(layer2_request)
                res["overall_confidence"] = layer1_sim
                res["layer2_triggered"] = True
                res["layer2_similarity"] = sim2
                res["layer2_result"] = "llm"
                if not res.get("concise_reason"):
                    res["concise_reason"] = (
                        f"Layer2 low similarity ({sim2}); LLM review of original product title."
                    )
                else:
                    res["concise_reason"] = (
                        f"Layer2 low ({sim2}) → LLM: {res['concise_reason']}"
                    )
                return res
            except Exception as llm_exc:
                # LLM failure on Layer2: keep Layer1 BI approve (failure-safe)
                return {
                    "offer_id": offer_id,
                    "flags": [],
                    "concise_reason": (
                        f"BI Layer Approved: High semantic similarity match ({layer1_sim}). "
                        f"Layer2 LLM failed after low original-product-MCAT ({sim2}): {llm_exc}"
                    ),
                    "overall_confidence": layer1_sim,
                    "layer2_triggered": True,
                    "layer2_similarity": sim2,
                    "layer2_result": "llm_error_fallback",
                }
        except Exception as exc:
            # Embedding failure: keep Layer 1 BI approval when Layer 2 cannot run.
            return {
                "offer_id": offer_id,
                "flags": [],
                "concise_reason": (
                    f"BI Layer Approved: High semantic similarity match ({layer1_sim}). "
                    f"Layer2 skipped due to error: {exc}"
                ),
                "overall_confidence": layer1_sim,
                "layer2_triggered": True,
                "layer2_similarity": None,
                "layer2_result": "error_fallback",
            }

    def review(self, request: dict[str, Any]) -> dict[str, Any]:
        offer_id = str(request.get("offer_id") or request.get("metadata", {}).get("offer_id") or "")
        title = str(request.get("title") or "")
        mcat = str(request.get("mcat") or "")
        # Option C: fetch the actual product title for every review. The public
        # payload remains unchanged and cannot override this independent signal.
        original_title = self._resolve_original_product_title(offer_id)

        # Layer 1: BL Title vs MCAT
        similarity = self.bi_engine.calculate_similarity(title, mcat)
        sim_val = round(float(similarity), 2)

        if similarity >= self.threshold:
            base = {
                "offer_id": offer_id,
                "flags": [],
                "concise_reason": f"BI Layer Approved: High semantic similarity match ({sim_val}).",
                "overall_confidence": sim_val,
                "layer2_triggered": False,
                "layer2_similarity": None,
                "layer2_result": "skipped",
            }

            # Layer 2: only when Layer 1 confidence is strictly above threshold and
            # original title exists. BI path is >= threshold; Layer 2 requires > threshold.
            if not self.layer2_enabled or sim_val <= self.threshold:
                return base

            if not original_title:
                base["layer2_result"] = "skipped_missing_original_title"
                return base

            return self._layer2_validate(
                offer_id=offer_id,
                original_title=original_title,
                mcat=mcat,
                layer1_sim=sim_val,
                request=request,
            )

        try:
            res = self.llm_agent.review(request)
            res["overall_confidence"] = sim_val
            res["layer2_triggered"] = False
            res["layer2_similarity"] = None
            res["layer2_result"] = "not_applicable"
            return res
        except Exception as e:
            return {
                "offer_id": offer_id,
                "flags": ["title_mcat_mismatch"],
                "concise_reason": f"BI Layer Mismatch: Cosine similarity low ({sim_val}). LLM fallback failed: {e}",
                "overall_confidence": sim_val,
                "layer2_triggered": False,
                "layer2_similarity": None,
                "layer2_result": "not_applicable",
            }


def build_bl_reviewer_agent(
    *,
    model: str,
    api_key: str | None,
    base_url: str | None,
    nlp_threshold: float = 0.60,
) -> HybridBLReviewerAgent:
    if not api_key or not base_url:
        raise ValueError("API key and base URL are required.")
    return HybridBLReviewerAgent(
        llm_agent=OpenAICompatibleBLReviewerAgent(model=model, api_key=api_key, base_url=base_url),
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
        start, end = text.find("{"), text.rfind("}")
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("LLM response must be a JSON object.")
    return parsed

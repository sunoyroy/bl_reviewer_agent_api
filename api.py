"""FastAPI application for the Buy Lead Reviewer Agent."""
from __future__ import annotations

import logging
import os
import sys
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

try:
    from .agent import build_bl_reviewer_agent
    from .input_parser import parse_review_request
except ImportError:  # pragma: no cover
    from agent import build_bl_reviewer_agent
    from input_parser import parse_review_request


class N8nReviewPayload(BaseModel):
    offer_id: str | None = Field(default=None)
    title: str | None = Field(default=None)
    mcat: str | None = Field(default=None)
    isq_filled: dict[str, Any] | str | None = Field(default=None)
    isq_asked: dict[str, Any] | list[str] | None = Field(default=None)
    eto_ofr_display_id: str | None = Field(default=None)
    eto_ofr_title: str | None = Field(default=None)
    glcat_mcat_name: str | None = Field(default=None)
    attributes_combined: str | None = Field(default=None)


# ==============================================================================
# UPDATED: Pydantic model to explicitly include overall_confidence
# ==============================================================================
class ReviewResult(BaseModel):
    offer_id: str | None = Field(default=None, examples=["146420001285"])
    flags: list[str]
    concise_reason: str
    overall_confidence: float | None = Field(default=None)


LOGGER = logging.getLogger(__name__)

app = FastAPI(title="Buy Lead Reviewer Agent API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(Exception)
def global_exception_handler(request: Request, exc: Exception):
    """Bulletproof exception handler that always extracts the core error message."""
    error_msg = repr(exc)
    LOGGER.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500, 
        content={"detail": "FUNCTION_INVOCATION_FAILED", "error": error_msg}
    )

# ==============================================================================
# Global Singleton Cache
# Ensures FastEmbed only writes files/loads models once per serverless cold start
# ==============================================================================
_CACHED_AGENT: Any = None

def _get_agent() -> Any:
    global _CACHED_AGENT
    if _CACHED_AGENT is None:
        api_key = os.getenv("LLM_GATEWAY_API_KEY")
        base_url = os.getenv("LLM_GATEWAY_BASE_URL", "https://imllm.intermesh.net/v1")
        model = os.getenv("LLM_GATEWAY_MODEL", "flex/openrouter/google/gemini-3-flash-preview")
        _CACHED_AGENT = build_bl_reviewer_agent(model=model, api_key=api_key, base_url=base_url)
    return _CACHED_AGENT


@app.get("/", tags=["Health"])
def root() -> dict[str, str]:
    return {"status": "ok", "message": "BL Reviewer Agent API is running"}


@app.get("/health", response_model=dict, tags=["Health"])
def health() -> dict:
    return {"status": "ok"}


# ==============================================================================
# UPDATED: Return the ReviewResult model instead of a generic dict
# ==============================================================================
@app.post("/review", response_model=ReviewResult, tags=["Review"])
def review_single(body: N8nReviewPayload) -> ReviewResult:
    try:
        agent = _get_agent()
        payload = body.model_dump(exclude_none=True)
        request = parse_review_request(payload)
        result = agent.review(request)
        
        # Explicitly return the structured model
        return ReviewResult(
            offer_id=result.get("offer_id"),
            flags=result.get("flags", []),
            concise_reason=result.get("concise_reason", "No reason provided."),
            overall_confidence=result.get("overall_confidence")
        )
    except Exception as exc:
        LOGGER.exception("Review failed for offer_id=%s", body.offer_id)
        raise HTTPException(status_code=500, detail=f"Request failed: {repr(exc)}")


@app.post("/batch", response_model=dict, tags=["Review"])
def review_batch(body: dict) -> dict:
    results = []
    leads = body.get("leads", [])
    
    try:
        agent = _get_agent()
    except Exception as exc:
        return {"results": [{"offer_id": lead.get("offer_id", ""), "flags": [], "concise_reason": f"Agent init error: {repr(exc)}"} for lead in leads]}

    for lead in leads:
        try:
            request = parse_review_request(lead)
            result = agent.review(request)
            results.append({
                "offer_id": result.get("offer_id"),
                "flags": result.get("flags", []),
                "concise_reason": result.get("concise_reason", "No reason provided."),
                "overall_confidence": result.get("overall_confidence")
            })
        except Exception as exc:
            offer_id = lead.get("offer_id", "")
            LOGGER.exception("Review failed for offer_id=%s", offer_id)
            results.append({
                "offer_id": offer_id,
                "flags": [],
                "concise_reason": f"Error: {repr(exc)[:120]}",
                "overall_confidence": 0.0
            })
    return {"results": results}
"""
FastAPI application for the Buy Lead Reviewer Agent.

Run with:
    uvicorn bl_reviewer_agent.api:app --host 0.0.0.0 --port 8000

Endpoints:
    POST /review       - Review a single buy lead
    POST /batch        - Review multiple buy leads
    GET  /health       - Health check
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import traceback
import sys

try:
    from .agent import build_bl_reviewer_agent, OpenAICompatibleBLReviewerAgent
    from .input_parser import parse_review_request
except ImportError:  # pragma: no cover - supports Vercel top-level module import
    from agent import build_bl_reviewer_agent, OpenAICompatibleBLReviewerAgent
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


LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Buy Lead Reviewer Agent API",
    description="Reviews IndiaMART buy leads for title/mcat/ISQ consistency.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
def global_exception_handler(request: Request, exc: Exception):
    """Return a JSON response containing the stack trace for debugging on Vercel.

    FIX: Uses format_exception(exc) instead of format_exc() to prevent 'NoneType: None' 
    masking at the middleware boundary.
    """
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    LOGGER.exception("Unhandled exception: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "FUNCTION_INVOCATION_FAILED", "trace": tb})


@app.get("/debug", tags=["Debug"])
def debug_info() -> dict[str, str]:
    """Small debug endpoint returning Python and environment hints."""
    return {
        "python": sys.version.splitlines()[0],
        "model_env": os.getenv("LLM_GATEWAY_MODEL", "<unset>"),
        "llm_key_present": "yes" if os.getenv("LLM_GATEWAY_API_KEY") else "no",
    }


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ReviewRequest(BaseModel):
    """Structured payload for lead review."""

    # Structured fields
    offer_id: str | None = Field(default=None, examples=["146420001285"])
    title: str | None = Field(default=None, examples=["BOPP Synthetic Non Tearable Sheets"])
    mcat: str | None = Field(default=None, examples=["Non Tearable Paper"])
    isq_filled: dict[str, Any] | str | None = Field(default=None)
    isq_asked: dict[str, Any] | list[str] | None = Field(default=None)


class ReviewResult(BaseModel):
    offer_id: str | None = Field(default=None, examples=["146420001285"])
    flags: list[str]
    concise_reason: str


class BatchRequest(BaseModel):
    leads: list[ReviewRequest]


class BatchResult(BaseModel):
    results: list[ReviewResult]


class HealthResponse(BaseModel):
    status: str
    model: str
    base_url: str


# ---------------------------------------------------------------------------
# Global Agent Singleton Cache
# ---------------------------------------------------------------------------

_CACHED_AGENT: Any = None

def _get_agent() -> Any:
    """Returns a globally cached agent instance to prevent re-initializing FastEmbed on every request."""
    global _CACHED_AGENT
    if _CACHED_AGENT is None:
        api_key = os.getenv("LLM_GATEWAY_API_KEY")
        base_url = os.getenv("LLM_GATEWAY_BASE_URL", "https://imllm.intermesh.net/v1")
        model = os.getenv("LLM_GATEWAY_MODEL", "google/gemini-3-flash-preview")
        _CACHED_AGENT = build_bl_reviewer_agent(model=model, api_key=api_key, base_url=base_url)
    return _CACHED_AGENT


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/", tags=["Health"])
def root() -> dict[str, str]:
    return {"status": "ok", "message": "BL Reviewer Agent API is running"}


@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health() -> HealthResponse:
    """Check that the service is running and environment is configured."""
    model = os.getenv("LLM_GATEWAY_MODEL", "google/gemini-3-flash-preview")
    return HealthResponse(
        status="ok",
        model=model,
        base_url=os.getenv("LLM_GATEWAY_BASE_URL", "https://imllm.intermesh.net/v1"),
    )


@app.post("/review", response_model=ReviewResult, tags=["Review"])
def review_single(body: N8nReviewPayload) -> ReviewResult:
    """
    Review a single buy lead.

    Accepts structured fields: `offer_id`, `title`, `mcat`, `isq_filled`, `isq_asked`.
    """
    payload = body.model_dump(exclude_none=True)
    try:
        # Crucial fix: Agent retrieval is moved inside the try block to cleanly capture errors
        agent = _get_agent()
        request = parse_review_request(payload)
        result = agent.review(request)
    except Exception as exc:
        LOGGER.exception("Review failed for offer_id=%s", body.offer_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
        
    return ReviewResult(
        offer_id=result.get("offer_id"),
        flags=result["flags"],
        concise_reason=result["concise_reason"],
    )


@app.post("/batch", response_model=BatchResult, tags=["Review"])
def review_batch(body: BatchRequest) -> BatchResult:
    """
    Review multiple buy leads in one call.
    """
    results: list[ReviewResult] = []
    for lead in body.leads:
        payload = lead.model_dump(exclude_none=True)
        try:
            agent = _get_agent()
            request = parse_review_request(payload)
            result = agent.review(request)
            results.append(
                ReviewResult(
                    offer_id=result.get("offer_id"),
                    flags=result["flags"],
                    concise_reason=result["concise_reason"],
                )
            )
        except Exception as exc:
            offer_id = lead.offer_id or ""
            LOGGER.exception("Review failed for offer_id=%s", offer_id)
            results.append(
                ReviewResult(
                    offer_id=offer_id,
                    flags=[],
                    concise_reason=f"Error: {str(exc)[:120]}",
                )
            )
    return BatchResult(results=results)
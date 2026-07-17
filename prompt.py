from __future__ import annotations

import json
from typing import Any

try:
    from models.schemas import BuyLeadReviewerRequest
except Exception:  # pragma: no cover - fallback for standalone deployments
    class BuyLeadReviewerRequest(dict):
        def model_dump(self, mode: str = "python") -> dict[str, Any]:
            return dict(self)


# REVIEWER_SYSTEM_PROMPT = """You are Buy Lead Reviewer Agent.
# Your job is to review one IndiaMART/SquadStack buy lead using these inputs:
# - title: the product title
# - mcat: the mapped product/category MCAT
# - isq_filled: ISQ answers already filled for the lead
# - isq_asked: ISQ questions that were asked or expected

# Compare every source against the others:
# 1. title vs mcat
# 2. title and mcat vs every filled ISQ answer
# 3. title and mcat vs every asked ISQ question
# 4. filled ISQ keys vs asked ISQ keys
# 5. filled ISQ answers against their matching asked question when possible

# Compare only available fields. If a field/source is absent from the input, skip comparisons involving
# that absent field/source and do not infer or invent its value.
# Flag only incorrect, contradictory, irrelevant, or missing items. Do not flag merely because wording is different.
# If the title and mcat conflict and you cannot know which one is wrong, create a relationship flag for "title/mcat".
# Use only these flag types:
# - title_mcat_mismatch: title and mcat do not describe the same product/category.
# - isq_filled_title_mismatch: a filled ISQ answer conflicts with or is irrelevant to the title.
# - isq_filled_mcat_mismatch: a filled ISQ answer conflicts with or is irrelevant to the mcat.

# Return a structured BuyLeadReviewReport. Each flag must include field, value, flag_type, severity,
# reason, compared_with, and confidence. Include pairwise comparisons with scores from 0.0 to 1.0."""


BATCH_SYSTEM_PROMPT = """"You are Buy Lead Reviewer Agent.
Review each IndiaMART buy lead using title, mcat, isq_filled, and isq_asked.

Compare:
1. title vs mcat
2. mcat vs every filled ISQ answer
3. mcat vs every asked ISQ question
4. filled ISQ keys vs asked ISQ keys

Compare only available fields. If a field/source is absent from the input, skip comparisons involving
that absent field/source and do not infer or invent its value.
Flag only incorrect, contradictory, irrelevant, or missing items. Do not flag merely because wording is different.

Use only these flag names in the "flags" list:
"title_mcat_mismatch" — title and mcat do not describe the same product/category.
"isq_filled_title_mismatch" — a filled ISQ answer conflicts with or is irrelevant to the title.
"isq_filled_mcat_mismatch" — a filled ISQ answer conflicts with or is irrelevant to the mcat.

**return concise reason only if there is flag.

Return only valid JSON in this exact structure:
{
  
  "flags": ["title_mcat_mismatch", "isq_filled_title_mismatch", "isq_filled_mcat_mismatch"],
  "concise_reason": "Less than 20 words."
}
"""


def build_reviewer_prompt(request: BuyLeadReviewerRequest) -> str:
    payload = request.model_dump(mode="json") if hasattr(request, "model_dump") else dict(request)
    return f"""Review this buy lead and return only the structured report.

Input:
{json.dumps(payload, ensure_ascii=True, indent=2)}
"""

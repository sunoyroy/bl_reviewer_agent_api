# Buy Lead Reviewer Agent — Flagging Layer Optimization

## 1. Executive Summary
This document provides a comprehensive, read-only architectural audit of the Buy Lead Reviewer Agent. The primary objective is to optimize the flagging layer to isolate major and critical business-impacting issues from minor discrepancies and semantic variations, thereby reducing noise in downstream dashboards and Google Sheets. The audit identifies critical architectural flaws—such as the BI embedding layer entirely bypassing ISQ checks on high Title-MCAT similarity—and prompt ambiguities that lead to over-flagging. A future state architecture and severity classification model are proposed to solve these issues.

## 2. Current Project Architecture
The system employs a **Hybrid Review Architecture**:
- **BI Layer**: Uses `LocalEmbeddingEngine` (`fastembed` with `paraphrase-multilingual-MiniLM-L12-v2`) to compare `title` and `mcat`. If cosine similarity $\ge 0.45$, it short-circuits and approves the lead.
- **LLM Layer**: If similarity $< 0.45$, it calls an OpenAI-compatible Gateway (`gemini-3-flash-preview`) to perform a nuanced review.
- **API**: A FastAPI app (`api.py`) exposing `/review` and `/batch`.
- **Integrations**: An N8N workflow (`Docs/Auditor (2).json`) that polls a Postgres database and writes flags to a Google Sheet, and a batch script (`batch_review.py`) for CSV processing.
- **Frontend**: A React/Vite application for manual CSV review and exporting.

## 3. Complete Flagging Data Flow
**Raw Buy Lead** -> **Postgres DB (via N8N)** -> **N8N Workflow** (`Docs/Auditor (2).json`)
-> **API** (`api.py` POST `/review`) -> **Input Parser** (`input_parser.py`) -> **Agent** (`agent.py: HybridBLReviewerAgent`)
-> **BI Layer**: Computes `title` vs `mcat` similarity. 
   - *Fast Path*: If $\ge 0.45$, returns `flags: []`.
   - *Fallback*: Calls LLM (`OpenAICompatibleBLReviewerAgent`) -> **Prompt** (`prompt.py: BATCH_SYSTEM_PROMPT`) -> **LLM Output (JSON)**
-> **API Response** -> **N8N Google Sheets Node** -> **Google Sheets / Dashboard**.

*Key Observation*: Flags flow directly from the LLM to the Google Sheet without any severity filtering or validation layer (other than `VALID_FLAG_NAMES` normalization in batch jobs).

## 4. Complete Flag Inventory
The system currently normalizes and recognizes three primary flags defined in the prompt and `batch_review.py`:

1. **`title_mcat_mismatch`**
   - **File**: `prompt.py`, `agent.py`, `batch_review.py`
   - **Function/Class**: `BATCH_SYSTEM_PROMPT`, `HybridBLReviewerAgent.review` (fallback error), `VALID_FLAG_NAMES`
   - **Comparison**: `title` vs `mcat`.
   - **Severity**: Currently treats all mismatches equally. 
   - **Recommendation**: KEEP BUT GATE (filter based on severity).

2. **`isq_filled_title_mismatch`**
   - **File**: `prompt.py`, `batch_review.py`
   - **Function**: `BATCH_SYSTEM_PROMPT`
   - **Comparison**: `isq_filled` answer conflicts with or is irrelevant to `title`.
   - **Severity**: Treats missing, irrelevant, and conflicting equally.
   - **Recommendation**: KEEP BUT GATE (only display explicit contradictions).

3. **`isq_filled_mcat_mismatch`**
   - **File**: `prompt.py`, `batch_review.py`
   - **Comparison**: `isq_filled` answer conflicts with or is irrelevant to `mcat`.
   - **Recommendation**: KEEP BUT GATE (only display if category identity is violated).

## 5. Title vs MCAT Analysis
Currently, `title` $\leftrightarrow$ `mcat` is evaluated first by the `LocalEmbeddingEngine`. 
- If `similarity >= 0.45`, it assumes the product is correct.
- If `similarity < 0.45`, it delegates to the LLM. 
- *Flaw*: Low similarity (e.g., synonyms or generic MCATs) triggers the LLM. The LLM prompt asks to flag "incorrect, contradictory, irrelevant, or missing items. Do not flag merely because wording is different." However, it fails to distinguish between a "Different product family" (Critical) and a "Related category but different product" (Major/Minor). 

## 6. MCAT vs ISQ Analysis
The prompt asks the LLM to compare "mcat vs every filled ISQ answer". 
- *Flaw*: The prompt says "Flag only ... irrelevant, or missing items". This can cause the LLM to flag an ISQ simply because it is an optional specification not explicitly covered by the broad MCAT.
- *Critical Bug*: Due to `agent.py` line 104 (`if similarity >= self.threshold:`), if the `title` and `mcat` match well, the agent returns immediately and **never checks the ISQs**. A lead could have a perfect Title/MCAT match but a completely contradictory ISQ, and it will be blindly approved.

## 7. Title vs ISQ Analysis
Similar to MCAT vs ISQ, the LLM is instructed to flag if an ISQ is "irrelevant to the title" (`isq_filled_title_mismatch`). 
- *Problem*: If a title is "Office Chair" and ISQ is "Color = Black", the LLM might interpret Color as "irrelevant" to the core title and flag it. The system currently cannot distinguish between an ISQ that adds valid information vs. an ISQ that contradicts the title.

## 8. Product Identity Analysis
The current system operates on direct pairwise string/semantic comparisons. It does not conceptually reason about **Product Identity**, **Product Family**, or **Category**.
- *Optimization Area*: The prompt and architecture should be refactored to first extract the core product identity from the title, and then check if the MCAT and ISQ support that identity, rather than just doing text comparisons.

## 9. Attribute Severity Analysis
All attributes are currently treated equally. An incorrect "Capacity" (Core attribute) generates the exact same flag as an incorrect "Color" (Secondary attribute).
- *Optimization Area*: The system must distinguish between Identity-defining attributes (P0), Commercially important attributes (P1), and Secondary attributes (P3). Only P0 and P1 should generate displayable flags.

## 10. Missing vs Contradictory Analysis
The `BATCH_SYSTEM_PROMPT` states: "Flag only incorrect, contradictory, irrelevant, or missing items."
- *Problem*: Explicitly instructing the LLM to flag "missing" items directly contradicts the instruction: "If a field/source is absent... skip comparisons". This creates a massive source of false positives where unspecified attributes are flagged as errors.

## 11. Prompt Analysis
- **File**: `prompt.py` (`BATCH_SYSTEM_PROMPT`)
- **Issues Found**:
  - Asks the model to find missing/irrelevant items.
  - Does not define criticality or severity.
  - Does not distinguish between missing, unknown, and contradictory.
  - Instructs the model to check "mcat vs every asked ISQ question" and "filled ISQ keys vs asked ISQ keys" but provides no valid flag types for these in the output schema!

## 12. Embedding and Threshold Analysis
- **Model**: `paraphrase-multilingual-MiniLM-L12-v2`
- **Threshold**: 0.45 (`agent.py`)
- **Observations**: 
  - The threshold is used as a fast-approval gate. 
  - *False Negatives*: High similarity incorrectly approves serious ISQ mismatches because the LLM is bypassed.
  - *Confidence Mixup*: `overall_confidence` is explicitly set to the cosine similarity value (`sim_val`) in `agent.py`. Confidence and Semantic Similarity are mathematically and conceptually different. 

## 13. API Analysis
- **File**: `api.py`
- **Endpoints**: `POST /review`, `POST /batch`
- **Output**: `ReviewResult` schema. Returns raw flags as a list of strings and a `concise_reason`.
- **Filtering**: No filtering exists in the API. All raw model observations are returned to downstream systems.

## 14. N8N / Google Sheets Analysis
- **File**: `Docs/Auditor (2).json`
- **Flow**: Retrieves data, hits API, maps API response (`flags`, `reason`, `confidence`) directly to Google Sheet columns.
- **Observation**: N8N writes everything blindly. Minor issues, informational flags, and hallucinations reach the sheet directly. The filter layer must conceptually sit before the API response or within the API layer.

## 15. Frontend Analysis
- **File**: `frontend/src/App.tsx`, `frontend/src/components/` (assumed based on structure)
- **Flow**: The frontend is a presentation layer for uploading CSVs and exporting them. It does not perform severity filtering.
- **Recommendation**: Keep the frontend as a pure presentation layer. The backend API must be the source of truth for criticality.

## 16. Batch / CSV Analysis
- **File**: `batch_review.py`
- **Flow**: Processes JSON, calls LLM, normalizes flags against `VALID_FLAG_NAMES`, and exports to CSV.
- **Observation**: If any flag is present, `status` becomes `needs_review` (Line 363). Minor suppressed findings will break the batch status if not filtered out prior to this logic.

## 17. False-Positive Sources
1. **Prompt "Missing/Irrelevant" Instruction**: `prompt.py`. Instructs LLM to flag missing items, causing massive noise for unspecified ISQs.
2. **LLM Fallback Catch-All**: `agent.py:116`. If the LLM call fails, it automatically returns `title_mcat_mismatch`. This pollutes the dashboard with false product mismatches when it's actually a system/network error.
3. **Lack of Severity Schema**: All differences become critical flags.

## 18. Recommended Severity Model
- **CRITICAL (P0)**: Wrong MCAT, different product category, contradictory core attribute. $\rightarrow$ **DISPLAY**
- **MAJOR (P1)**: Material specification contradiction (e.g., 5 HP vs 50 HP). $\rightarrow$ **DISPLAY**
- **MINOR (P2)**: Harmless wording differences, synonyms, secondary attribute mismatch (e.g., Color). $\rightarrow$ **HIDE**
- **INFORMATIONAL (P3)**: Missing/Unspecified attributes, valid additional info. $\rightarrow$ **HIDE**

## 19. Recommended Confidence Model
Disconnect `overall_confidence` from `cosine_similarity`.
The LLM should output a distinct confidence score (e.g., 0.0 to 1.0) based on its certainty of the contradiction.
- High Confidence + Critical Severity = DISPLAY
- Low Confidence + Critical Severity = MANUAL REVIEW REQUIRED

## 20. Root-Cause Deduplication
Currently, a bad MCAT will trigger `title_mcat_mismatch` AND `isq_filled_mcat_mismatch`.
- **Recommendation**: Move toward root-cause flags:
  - `CATEGORY_MAPPING_ERROR`
  - `PRODUCT_IDENTITY_CONFLICT`
  - `ATTRIBUTE_CONTRADICTION`
  - `SYSTEM_ERROR`

## 21. Recommended Filtering Architecture
```text
Review Engine
 ↓
All Internal Findings (CRITICAL, MAJOR, MINOR, INFO)
 ↓
Severity / Criticality Filter (API Layer or Agent Orchestrator)
 ↓
Displayable Findings (CRITICAL/MAJOR Only)
 ↓
API Response (ReviewResult)
```

## 22. Golden Dataset / Validation Strategy
A test suite should be created encompassing:
- **Correct cases**: No issue.
- **Minor mismatch cases**: Different wording, unspecified ISQ (Expect: HIDE).
- **Major/Critical mismatch cases**: Wrong MCAT, numerical contradiction (Expect: DISPLAY).
- **Metrics**: Optimize for High Critical Recall and Low False Positive Rate.

## 23. Prioritized Optimization Plan
1. **P0 - Fix BI Layer Short-Circuit**: Modify `agent.py` so the BI layer does not bypass ISQ checks when title and MCAT match.
2. **P0 - Fix Prompt Contradictions**: Remove "missing/irrelevant" from `BATCH_SYSTEM_PROMPT`.
3. **P1 - Implement Severity Classification**: Update the LLM schema to return `severity` and filter out MINOR/INFO in `api.py`.
4. **P1 - Fix Exception Handling**: Stop using `title_mcat_mismatch` as a catch-all network error flag in `agent.py`.
5. **P2 - Decouple Confidence**: Ask the LLM for confidence rather than hardcoding similarity.

## 24. Risks and Trade-offs
- **Risk**: Routing all leads through the LLM for ISQ checks (removing the BI short-circuit) will increase LLM Gateway costs and latency. 
- **Trade-off**: To maintain low costs, the BI layer could be expanded to also embed ISQ strings, but semantic similarity on key-value pairs is notoriously unreliable.

## 25. Exact Files / Functions Requiring Future Changes

1. **`agent.py`**
   - *Class*: `HybridBLReviewerAgent.review`
   - *Change*: Remove the early return `if similarity >= self.threshold:` OR implement a secondary check for ISQ presence. Stop returning `title_mcat_mismatch` on Exception.
2. **`prompt.py`**
   - *Variable*: `BATCH_SYSTEM_PROMPT`
   - *Change*: Instruct the model to assign severity. Remove instructions to flag "missing/irrelevant" items. Define Product Identity logic.
3. **`api.py`**
   - *Function*: `review_single`, `review_batch`
   - *Change*: Introduce a filtering function that strips out MINOR/INFO flags before returning the `ReviewResult` to N8N.
4. **`batch_review.py`**
   - *Function*: `result_to_flat`
   - *Change*: Update `status` logic to only trigger `needs_review` on CRITICAL or MAJOR flags.

## 26. Recommended Future Architecture
**CURRENT ARCHITECTURE**:
```text
Input -> Normalization -> BI Fast Screen (Bypasses ISQ) -> LLM -> Raw Output -> API -> N8N -> Sheet
```

**RECOMMENDED FUTURE ARCHITECTURE**:
```text
Input
 ↓
Normalization
 ↓
Fast Semantic Screening (Flags obvious title/MCAT matches, but still queues ISQ for review)
 ↓
Deep Review (LLM evaluates Identity, Contradiction vs Missing)
 ↓
Internal Findings (All flags with Severity)
 ↓
Criticality & Severity Filter (Strips Minor/Info)
 ↓
Displayable Findings
 ↓
API
 ↓
N8N / Frontend
 ↓
Google Sheet / Dashboard
```

## 27. Final Conclusion
The Buy Lead Reviewer Agent is fundamentally over-flagging because the LLM is instructed to flag "missing" and "irrelevant" data, and there is no downstream filtering layer based on business severity. Simultaneously, it is likely generating false negatives due to a BI layer that aggressively short-circuits LLM review on high Title-MCAT similarity, entirely ignoring contradictory ISQs. By updating the prompt to prioritize explicit contradictions, decoupling similarity from confidence, and introducing a Severity Filter in the API layer, the dashboard noise can be drastically reduced without losing visibility into critical product mismatches.

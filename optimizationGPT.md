# Buy Lead Reviewer Agent — Flagging Layer Optimization Plan

## 1. Purpose

This document defines a **read-only analysis and optimization plan** for thinning the Buy Lead Reviewer Agent's flagging layer.

### Primary objective

The current system can identify differences across buy-lead attributes, but the dashboard/Google Sheet should **not expose every semantic or minor inconsistency**.

The desired behavior is:

> **Only surface major, business-critical mismatches that indicate a materially wrong lead, incorrect MCAT mapping, or a serious inconsistency between the lead's intent and its attributes.**

Minor wording differences, harmless semantic variations, incomplete-but-acceptable attributes, and low-confidence discrepancies should remain hidden from the dashboard output.

### Important constraint

This document is an analysis/design specification only.

**Do not implement any of the recommendations in this document.**
Do not modify source files, prompts, thresholds, schemas, APIs, frontend behavior, N8N workflows, or deployment configuration while performing this analysis.

---

# 2. Current Architecture Relevant to Flagging

Based on `IMPLEMENTATION.md`, the current system follows a hybrid review architecture:

1. A local embedding layer uses `fastembed` with `paraphrase-multilingual-MiniLM-L12-v2`.
2. The title and MCAT are compared using cosine similarity.
3. If similarity is sufficiently high, the lead can receive a fast approval.
4. If the similarity is below the configured threshold, the request is sent to an OpenAI-compatible LLM gateway.
5. The LLM performs deeper comparisons and produces structured JSON flags.
6. The backend exposes the review through `POST /review` and `POST /batch`.
7. Downstream N8N automation parses the result and writes data to Google Sheets.
8. The frontend can also process/export CSV review results.

The current LLM prompt is documented as checking:

- `title` vs `mcat`
- `mcat` vs `isq_filled`
- `isq_keys` vs `isq_asked`

with structured flags such as:

- `title_mcat_mismatch`
- `isq_filled_title_mismatch`

The optimization should therefore focus on **the decision boundary between "difference detected" and "critical issue worth displaying."**

---

# 3. Core Problem

The system should not treat:

> "something is different"

as equivalent to:

> "the buy lead is materially wrong."

These are two different concepts.

The recommended conceptual model is:

```text
Raw Difference
      |
      v
Is it actually inconsistent?
      |
      v
Is the inconsistency material?
      |
      v
Can it affect MCAT / buyer intent / lead quality?
      |
      v
Is confidence high enough?
      |
      v
CRITICAL FLAG
```

Only the final stage should reach the dashboard/sheet's primary flagging output.

---

# 4. Define the New Flagging Philosophy

The optimization should move the system from a broad **mismatch detector** toward a **critical issue detector**.

## 4.1 Difference ≠ mismatch

Examples that should generally NOT be surfaced:

- singular vs plural differences
- word-order differences
- common synonyms
- abbreviations
- spelling variations that preserve meaning
- minor descriptive differences
- optional attributes that do not affect product identity
- formatting differences
- generic product descriptors
- slightly different but compatible ISQ values
- missing non-essential attributes
- semantic similarity that is imperfect but still clearly within the same product family

These may still be useful internally for reasoning, but they should not automatically become dashboard flags.

## 4.2 Critical mismatch

A mismatch should be considered critical when it can reasonably indicate one of the following:

1. **Wrong MCAT/product-category mapping**
2. **Different product or product family**
3. **Contradictory buyer intent**
4. **A major attribute conflict that changes what is being requested**
5. **An ISQ value that directly contradicts the title/product intent**
6. **A category mismatch severe enough that the lead could be routed to the wrong business category**
7. **A clearly incompatible product characteristic**
8. **A high-confidence semantic contradiction rather than merely low similarity**

---

# 5. Highest-Priority Optimization: MCAT Mapping

The MCAT relationship should be treated as the highest-priority signal.

The central question should not simply be:

> "Are title and MCAT semantically similar?"

It should be:

> "Does the MCAT represent the same actual product/category implied by the buyer's title and intent?"

## Critical examples

A critical issue would be a case where:

```text
Title → Car Door
MCAT  → Mobile Phone
```

or:

```text
Title → Industrial Water Pump
MCAT  → Women's Clothing
```

or any similarly obvious category/product-family conflict.

These should be surfaced even if other fields look internally consistent.

## Recommended MCAT severity hierarchy

### P0 — Critical

The title and MCAT clearly refer to unrelated product categories.

Action:

```text
DISPLAY FLAG
```

### P1 — Major

The title and MCAT belong to related domains but clearly different product families.

Action:

```text
DISPLAY FLAG
```

### P2 — Minor

The wording differs but the actual product/category is still compatible.

Action:

```text
DO NOT DISPLAY
```

### P3 — Noise

Formatting, wording, synonym, abbreviation, or generic descriptor difference.

Action:

```text
DO NOT DISPLAY
```

---

# 6. Separate Product Identity From Attribute Differences

One major source of over-flagging is treating all attributes with the same severity.

The system should conceptually classify fields into:

### Tier A — Identity-defining

These can change the product being requested.

Examples:

- product type
- product family
- model/product identity
- core material when it defines the product
- application/use-case when it changes product category
- critical physical characteristic
- major equipment type
- major industry/category

A contradiction here can be critical.

### Tier B — Commercially important

These can affect buyer requirements but do not necessarily change the product identity.

Examples:

- size
- capacity
- voltage
- dimensions
- grade
- quantity
- specification values

These should be flagged only when the conflict is explicit and material.

### Tier C — Descriptive / optional

Examples:

- color
- generic descriptors
- wording variations
- secondary properties
- non-essential qualifiers

These should generally not be displayed unless the source text makes the conflict explicit and commercially meaningful.

---

# 7. Title vs MCAT Optimization

The current architecture explicitly evaluates title vs MCAT.

The optimization should make this comparison **intent/category aware** rather than purely similarity based.

## Recommended decision logic

Conceptually:

```text
Compare title and MCAT
        |
        +--> Same product/category?
        |       |
        |       +--> YES → No flag
        |
        +--> Different wording but same intent?
        |       |
        |       +--> YES → No flag
        |
        +--> Related but different product family?
        |       |
        |       +--> YES → Major flag
        |
        +--> Clearly unrelated?
                |
                +--> Critical flag
```

## Important principle

A low embedding similarity score should **not automatically mean critical mismatch**.

Embedding similarity should be treated as:

```text
candidate-generation / confidence signal
```

rather than:

```text
business-severity signal
```

This is especially important because semantically related products can have different textual representations.

---

# 8. MCAT vs ISQ Optimization

The current system also compares MCAT against filled ISQ values.

This relationship should be treated differently from title-vs-MCAT.

## Critical case

An ISQ value explicitly identifies a product/category that contradicts the MCAT.

Example conceptually:

```text
MCAT → Industrial Pump
ISQ → Smartphone Model
```

This is a strong candidate for a critical flag.

## Non-critical case

The ISQ contains a value that is:

- optional
- more specific
- a normal variant
- a compatible specification
- absent from the MCAT wording but not contradictory

This should not automatically become a flag.

## Key rule

The system should distinguish:

```text
ISQ is not mentioned by MCAT
```

from:

```text
ISQ contradicts MCAT
```

Only the second is normally a serious issue.

---

# 9. ISQ Filled vs Title Optimization

This comparison should focus primarily on **contradiction**, not completeness.

### Should be surfaced

If:

```text
Title → Diesel Generator
ISQ → Electric Motor
```

or:

```text
Title → 5 HP Pump
ISQ → 100 HP
```

where the difference materially changes the requested product/specification.

### Should not be surfaced

If:

```text
Title → Stainless Steel Water Bottle
ISQ → Material = Stainless Steel
```

No issue.

Also avoid flagging:

```text
Title → Office Chair
ISQ → Color = Black
```

unless the title explicitly requires a conflicting color.

---

# 10. Distinguish Missing Information From Contradictory Information

This is one of the most important filters.

The following are different:

### Missing

```text
Title: Industrial Pump
ISQ: Capacity = ""
```

This is not necessarily an error.

### Unknown

```text
Title: Industrial Pump
ISQ: Voltage = not specified
```

Not necessarily an error.

### Contradictory

```text
Title: 5 HP Pump
ISQ: Capacity = 50 HP
```

Potentially critical.

Therefore the flagging layer should prioritize:

```text
CONTRADICTION > ABSENCE
```

and:

```text
EXPLICIT CONFLICT > INFERRED DIFFERENCE
```

---

# 11. Introduce Severity Before Display

The analysis recommends a conceptual two-stage output.

## Stage 1 — Internal review

The model can continue identifying:

- possible mismatch
- possible contradiction
- semantic difference
- uncertainty
- missing information

## Stage 2 — Display filter

Only issues satisfying the criticality rules are emitted to the dashboard/sheet.

Conceptually:

```json
{
  "issue_detected": true,
  "severity": "critical",
  "display": true
}
```

versus:

```json
{
  "issue_detected": true,
  "severity": "minor",
  "display": false
}
```

The exact schema should be decided only after inspecting the actual implementation.

---

# 12. Recommended Severity Model

Use a small number of severity classes.

## Critical

Clearly wrong and materially harmful.

Examples:

- wrong MCAT
- unrelated product category
- contradictory product identity
- major specification contradiction
- explicit product-family conflict

Display:

```text
YES
```

## Major

Likely meaningful mismatch that can affect classification or buyer intent.

Examples:

- related but clearly different product family
- important attribute contradiction
- significant ISQ/title conflict

Display:

```text
YES
```

## Minor

Potential inconsistency but unlikely to affect lead quality.

Examples:

- wording differences
- optional attribute differences
- low-impact specification variation

Display:

```text
NO
```

## Informational

Useful for internal reasoning but not a problem.

Display:

```text
NO
```

---

# 13. Confidence and Severity Must Be Separate

Do not combine confidence and severity into a single number.

These represent different concepts.

### Confidence

How certain is the model that a mismatch exists?

### Severity

How harmful would that mismatch be if it exists?

Example:

```text
Confidence = 0.95
Severity = Minor
```

should still not reach the dashboard.

Conversely:

```text
Confidence = 0.82
Severity = Critical
```

may deserve investigation/display depending on the agreed threshold.

The important principle is:

```text
HIGH CONFIDENCE + LOW SEVERITY = HIDE
HIGH SEVERITY + SUFFICIENT CONFIDENCE = DISPLAY
```

---

# 14. Avoid Using Embedding Threshold Alone

The local embedding layer currently provides a fast approval path based on similarity.

The optimization should investigate whether this shortcut can hide or expose the wrong cases.

The analysis should specifically inspect:

- current threshold values
- how the threshold is used
- whether similarity is symmetric
- whether title length affects similarity
- whether MCAT labels are short/generic
- whether false positives occur around related categories
- whether false negatives occur for legitimate product variants

Do not change the threshold during this task.

Instead, document:

1. current behavior
2. potential failure modes
3. evidence required before changing it
4. recommended validation dataset

---

# 15. Prompt-Level Optimization

The prompt is currently responsible for nuanced comparisons and structured flag generation.

The prompt should conceptually be changed from:

```text
Find mismatches.
```

to:

```text
Find only material contradictions that can indicate a genuinely incorrect
product/category/lead mapping.
```

The final implementation prompt should explicitly instruct the model to:

1. prioritize product identity
2. prioritize MCAT correctness
3. detect explicit contradictions
4. ignore harmless wording differences
5. ignore synonyms
6. ignore compatible variants
7. ignore missing optional information
8. avoid inferring contradictions without sufficient evidence
9. assign severity
10. only return displayable issues when severity is critical/major and confidence is sufficient

Do not implement these prompt changes during this analysis.

---

# 16. Add a "Do Not Flag" Policy

A strong anti-noise prompt should explicitly contain negative examples.

The future prompt should tell the model not to flag:

- synonyms
- abbreviations
- pluralization
- minor spelling differences
- word-order differences
- generic descriptors
- compatible product variants
- attributes not present in the title unless they contradict something
- unspecified values
- additional valid details
- differences that do not change buyer intent

This is likely to be as important as defining what should be flagged.

---

# 17. Use Explicit Contradiction Detection

The most reliable signals should be contradiction patterns.

Examples:

```text
A says X
B explicitly says not-X
```

or:

```text
A = 5 HP
B = 50 HP
```

or:

```text
A = diesel
B = electric
```

or:

```text
A = car door
B = mobile phone
```

These are stronger than generic semantic distance.

Therefore, the future architecture should prioritize:

```text
Explicit contradiction
        ↓
Identity conflict
        ↓
Material attribute conflict
        ↓
Semantic mismatch
        ↓
Minor difference
```

and only the upper portion should be exposed.

---

# 18. Flag Deduplication

The dashboard should avoid showing multiple flags for the same underlying problem.

Example:

```text
title_mcat_mismatch
mcat_isq_mismatch
isq_title_mismatch
```

may all be consequences of one underlying product-category error.

Instead of showing three independent issues, the system should ideally group them into one root-cause issue.

Conceptually:

```text
Root Cause:
Incorrect product/category mapping

Evidence:
- Title indicates X
- MCAT indicates Y
- ISQ supports X
```

This produces a cleaner dashboard and reduces perceived noise.

---

# 19. Root-Cause-First Flagging

The future optimization should classify issues by root cause.

Suggested categories:

### CATEGORY_MAPPING_ERROR

MCAT does not represent the product indicated by the title/intent.

### PRODUCT_IDENTITY_CONFLICT

Different products/product families are being referenced.

### ATTRIBUTE_CONTRADICTION

A material attribute conflicts with the requested product.

### ISQ_INTENT_CONFLICT

Filled ISQ information contradicts buyer intent.

### OTHER_CRITICAL_INCONSISTENCY

A serious issue not covered by the above.

Minor differences should not receive root-cause flags.

---

# 20. Recommended Output Contract

The exact schema must be verified against the existing code before implementation.

Conceptually, the API should distinguish:

### Internal result

```text
all observations
```

from:

### Dashboard result

```text
only critical/major issues
```

For example:

```json
{
  "critical_flags": [
    {
      "type": "CATEGORY_MAPPING_ERROR",
      "severity": "critical",
      "reason": "MCAT represents a different product category from the buyer title."
    }
  ]
}
```

The final API should not expose internal reasoning merely because the model detected a difference.

---

# 21. Dashboard / Google Sheet Optimization

According to the current implementation documentation, N8N can parse the API result and append/update Google Sheets.

Therefore, the most important downstream optimization is to ensure that the **sheet receives the filtered result**, rather than relying only on frontend filtering.

Recommended conceptual flow:

```text
Lead
 ↓
Review engine
 ↓
All internal observations
 ↓
Severity/root-cause filter
 ↓
Critical/major issues only
 ↓
API response
 ↓
N8N
 ↓
Google Sheet
 ↓
Dashboard
```

This prevents minor flags from leaking into downstream systems.

---

# 22. Batch API Considerations

The `/batch` endpoint processes leads sequentially and catches individual failures.

The optimization should verify that:

- one noisy lead does not affect another
- filtering is applied independently per lead
- empty critical-flag results are represented consistently
- batch output does not accidentally include raw/internal mismatch data
- downstream CSV generation does not reintroduce suppressed flags

No batch implementation changes should be made during this analysis.

---

# 23. Frontend Considerations

The frontend currently allows CSV upload, processing, and export.

The analysis should verify whether the frontend:

- directly displays raw API flags
- applies any independent filtering
- has duplicate flag rendering
- displays reasons that should remain internal
- exports hidden/minor issues
- assumes every detected mismatch is dashboard-worthy

The preferred architecture is:

> **Business-critical filtering should happen in the backend API, not only in the frontend.**

Frontend filtering should be considered presentation logic, not the primary correctness layer.

---

# 24. N8N Integration Considerations

The documentation identifies N8N as a primary downstream consumer.

The analysis should inspect `Docs/Auditor (2).json` and determine:

- which API fields are consumed
- whether all flags are written to Sheets
- whether filtering currently happens in N8N
- whether empty flags are handled
- whether multiple flags are concatenated
- whether raw LLM output is persisted
- whether the sheet has separate columns for different mismatch types

Do not modify the workflow.

Document only what is currently happening and where the filter should conceptually sit.

---

# 25. Validation Dataset Is Essential

Before changing thresholds or prompts, create a labeled validation set.

Recommended categories:

### Class A — Correct

No critical mismatch.

### Class B — Minor mismatch

Difference exists but should NOT be displayed.

### Class C — Major mismatch

Should be displayed.

### Class D — Critical mismatch

Must be displayed.

The most important metric should not simply be total flag count.

Track:

```text
Critical Precision
Critical Recall
False Positive Rate
False Negative Rate
```

The key optimization target is:

> **Reduce false-positive flags without allowing critical mismatches to disappear.**

---

# 26. Build a Golden Set

A golden dataset should contain real examples covering:

- correct title/MCAT pairs
- obviously wrong MCAT mappings
- related MCATs
- near-neighbor categories
- different product families
- synonyms
- abbreviations
- spelling variations
- conflicting ISQs
- compatible ISQs
- missing ISQs
- contradictory numeric specifications
- contradictory product attributes

Each example should have a human-reviewed expected result:

```text
DISPLAY
or
DO NOT DISPLAY
```

This becomes the benchmark for future prompt/threshold changes.

---

# 27. Recommended Evaluation Matrix

For every existing flag type, evaluate:

| Flag Area | Difference Detected? | Material? | Critical? | Display? |
|---|---:|---:|---:|---:|
| Title ↔ MCAT | Yes/No | Yes/No | Yes/No | Yes/No |
| MCAT ↔ ISQ | Yes/No | Yes/No | Yes/No | Yes/No |
| Title ↔ ISQ | Yes/No | Yes/No | Yes/No | Yes/No |

The important shift is adding:

```text
Material?
Critical?
```

between detection and display.

---

# 28. Recommended Analysis of Existing Flags

For the current implementation, inspect every flag field and classify it as:

### Keep

High-value critical issue.

### Keep but Gate

Useful signal, but only display under severity/confidence conditions.

### Internal Only

Useful for model reasoning/debugging but not dashboard output.

### Remove From Display

Consistently noisy or low-value.

Do not actually remove anything during this task.

---

# 29. Investigate False-Positive Sources

The full project review should explicitly look for these sources of noise:

1. Embedding threshold too aggressive
2. Prompt interpreting any difference as mismatch
3. Lack of severity classification
4. No distinction between missing and contradictory
5. No product-identity prioritization
6. Overly broad ISQ comparison
7. Model inference without evidence
8. Duplicate flags for one root cause
9. Frontend showing raw API results
10. N8N persisting all model-generated observations
11. Batch/CSV output bypassing the intended filtering layer
12. Inconsistent empty/null handling

Each discovered source should be documented with:

```text
File
Function
Current behavior
Why it creates noise
Recommended optimization
Risk
Validation required
```

---

# 30. Recommended Investigation Order

The Anti-Gravity/Cursor agent should review the repository in this order:

## Part 1 — Repository inventory

Identify:

- backend files
- frontend files
- prompt files
- API schemas
- parsers
- batch processing
- N8N workflow files
- configuration
- tests
- documentation

Do not modify anything.

## Part 2 — Trace input

Follow:

```text
raw lead
→ input_parser
→ normalized payload
→ API
→ reviewer agent
```

Document every transformation.

## Part 3 — Trace review logic

Follow:

```text
normalized lead
→ local embedding
→ threshold decision
→ LLM
→ structured output
```

Document exact conditions.

## Part 4 — Trace every flag

For every mismatch/flag:

```text
Where created?
Why created?
What evidence is used?
What threshold exists?
Where returned?
Where consumed?
```

## Part 5 — Trace downstream display

Follow:

```text
API response
→ N8N / frontend
→ Sheet / CSV
→ dashboard
```

Identify where non-critical flags become visible.

## Part 6 — Identify optimization points

Classify each opportunity as:

```text
Prompt-level
Logic-level
Schema-level
Threshold-level
Aggregation-level
Downstream-filter-level
UI-level
```

## Part 7 — Produce recommendations

Rank every recommendation:

```text
P0 — Critical
P1 — High
P2 — Medium
P3 — Optional
```

---

# 31. Anti-Gravity Analysis Prompt

The following prompt is intended to be given to Anti-Gravity/Cursor.

**Important: This is an analysis-only task.**

```text
You are reviewing the entire Buy Lead Reviewer Agent project.

TASK:
Perform a complete read-only architecture and flagging-layer audit.

DO NOT:
- modify any source file
- modify prompts
- modify thresholds
- modify API schemas
- modify frontend code
- modify N8N workflows
- create commits
- rename files
- delete files
- change configuration
- deploy anything
- run automatic code fixes

The ONLY allowed output artifact is:

optimization.md

The goal is to determine how we can THIN THE FLAGGING LAYER so that the API/dashboard/Google Sheet exposes ONLY major and critical buy-lead inconsistencies.

The system should NOT surface every difference.

The target behavior is:

RAW DIFFERENCE
→ validate actual inconsistency
→ determine materiality
→ determine business severity
→ determine confidence
→ display only major/critical issues

PRIMARY BUSINESS PRIORITY:

1. Wrong MCAT/product-category mapping
2. Different product/product family
3. Major contradiction in buyer intent
4. Material attribute/specification contradiction
5. Strong title/MCAT/ISQ conflict

Do NOT treat these as automatically critical:

- synonyms
- abbreviations
- spelling variations
- singular/plural differences
- word-order differences
- harmless semantic differences
- optional attributes
- missing information
- unspecified values
- compatible variants
- additional valid details
- low similarity without an actual contradiction

IMPORTANT:
A difference is NOT automatically a mismatch.
A mismatch is NOT automatically critical.

Review the entire repository, not only the documented backend files.

==================================================
PART 1 — INVENTORY
==================================================

Identify all relevant:

- backend files
- frontend files
- prompt files
- API schemas
- Pydantic models
- input parsers
- agent/reviewer classes
- embedding logic
- thresholds
- batch processing
- CSV generation
- N8N workflow files
- Google Sheet integration
- dashboard rendering
- tests
- configuration
- deployment files

For each relevant file provide:
- path
- purpose
- relevance to flagging

==================================================
PART 2 — TRACE THE COMPLETE DATA FLOW
==================================================

Trace the actual implementation:

raw lead
→ parser
→ normalized payload
→ local embedding layer
→ threshold decision
→ LLM layer
→ structured review
→ API response
→ N8N/frontend
→ Google Sheet/CSV/dashboard

Do not assume the documentation is complete.
Verify everything against the actual repository.

For every transition identify:
- input
- output
- transformations
- filtering
- flag creation
- flag suppression
- possible noise introduction

==================================================
PART 3 — TRACE EVERY FLAG
==================================================

Find every flag/mismatch/error field generated anywhere in the project.

For EACH flag document:

1. exact field name
2. file path
3. function/class
4. line number(s)
5. source data used
6. decision logic
7. prompt instruction if applicable
8. threshold if applicable
9. downstream consumer
10. whether it reaches API output
11. whether it reaches N8N
12. whether it reaches Google Sheets
13. whether it reaches frontend/dashboard
14. likely false-positive sources
15. business severity
16. recommendation:
   - KEEP
   - KEEP BUT GATE
   - INTERNAL ONLY
   - DO NOT DISPLAY

Do not change the code.

==================================================
PART 4 — TITLE vs MCAT
==================================================

Deeply analyze title/MCAT comparison.

Determine:

- how similarity is calculated
- exact embedding model
- exact thresholds
- fast-approval behavior
- LLM fallback behavior
- how semantic similarity maps to mismatch
- whether low similarity is treated as an error
- whether product identity is explicitly evaluated
- whether category hierarchy is considered
- whether related categories are distinguished from unrelated categories

Identify cases where the current architecture could over-flag.

Give recommendations for detecting:

CRITICAL:
- unrelated MCAT
- wrong product category
- different product family
- strong product identity conflict

NON-CRITICAL:
- synonyms
- variants
- wording differences
- related category terminology

Do not change thresholds.

==================================================
PART 5 — MCAT vs ISQ
==================================================

Analyze every MCAT/ISQ comparison.

Explicitly distinguish:

- ISQ missing
- ISQ unspecified
- ISQ adds valid detail
- ISQ differs harmlessly
- ISQ materially conflicts
- ISQ identifies a different product

Determine which cases should be dashboard-visible.

==================================================
PART 6 — TITLE vs ISQ
==================================================

Analyze title/ISQ comparison.

Prioritize explicit contradiction.

Examples of serious issues:

Title = 5 HP pump
ISQ = 50 HP

Title = diesel generator
ISQ = electric motor

Do NOT treat every missing title attribute as an error.

Document exact current behavior and recommended filtering.

==================================================
PART 7 — SEVERITY MODEL
==================================================

Design a recommended conceptual severity model:

CRITICAL
MAJOR
MINOR
INFORMATIONAL

For each current flag identify the recommended severity.

Do not implement severity.

Explain:

- why the severity is appropriate
- what evidence is required
- whether it should be displayed

==================================================
PART 8 — CONFIDENCE vs SEVERITY
==================================================

Determine whether the current system mixes confidence and severity.

Recommend keeping them conceptually separate.

Analyze:

HIGH CONFIDENCE + LOW SEVERITY
HIGH CONFIDENCE + HIGH SEVERITY
LOW CONFIDENCE + HIGH SEVERITY
LOW CONFIDENCE + LOW SEVERITY

Explain what should reach the dashboard.

==================================================
PART 9 — ROOT-CAUSE DEDUPLICATION
==================================================

Determine whether multiple current flags can represent the same underlying issue.

For example:

title_mcat_mismatch
mcat_isq_mismatch
isq_title_mismatch

may all indicate one root cause.

Identify duplicate/overlapping flag scenarios.

Recommend a root-cause-first model such as:

CATEGORY_MAPPING_ERROR
PRODUCT_IDENTITY_CONFLICT
ATTRIBUTE_CONTRADICTION
ISQ_INTENT_CONFLICT
OTHER_CRITICAL_INCONSISTENCY

Do not implement it.

==================================================
PART 10 — API OUTPUT
==================================================

Trace exactly what /review and /batch return.

Determine:

- raw flags returned?
- filtered flags returned?
- internal reasoning returned?
- severity returned?
- confidence returned?
- duplicate flags possible?
- empty results represented consistently?

Identify the best conceptual point for filtering.

The preferred target is:

internal observations
→ severity/root-cause filter
→ API exposes displayable issues

Do not modify the API.

==================================================
PART 11 — N8N / GOOGLE SHEETS
==================================================

Inspect the actual N8N workflow(s).

Determine:

- exact API fields consumed
- whether filtering happens
- whether raw LLM results are stored
- how flags are concatenated
- whether empty flags are handled
- whether multiple flags become multiple sheet entries
- whether the sheet/dashboard can receive minor flags

Recommend where filtering SHOULD conceptually occur.

Do not modify N8N.

==================================================
PART 12 — FRONTEND
==================================================

Inspect the frontend.

Determine:

- where API flags are rendered
- whether raw flags are displayed
- whether frontend filtering exists
- whether CSV export includes hidden/minor flags
- whether UI assumes every mismatch is important

Recommend backend-vs-frontend filtering responsibilities.

Do not modify frontend.

==================================================
PART 13 — FALSE POSITIVE ANALYSIS
==================================================

Identify every likely source of over-flagging.

Classify each as:

PROMPT
EMBEDDING
THRESHOLD
BUSINESS LOGIC
SCHEMA
PARSER
AGGREGATION
N8N
FRONTEND

For each issue provide:

- exact location
- current behavior
- why it creates noise
- severity
- recommended fix
- validation needed
- implementation risk

==================================================
PART 14 — GOLDEN DATASET
==================================================

Recommend a validation dataset containing:

A. Correct leads
B. Minor mismatches
C. Major mismatches
D. Critical mismatches

Include examples covering:

- wrong MCAT
- unrelated categories
- related categories
- different product families
- synonyms
- abbreviations
- spelling variation
- numeric contradictions
- product attribute contradictions
- missing ISQ
- unspecified ISQ
- valid additional ISQ information
- contradictory ISQ
- title/ISQ conflict

Recommend evaluation metrics:

- Critical Precision
- Critical Recall
- False Positive Rate
- False Negative Rate

The primary objective is:

REDUCE FALSE POSITIVES WITHOUT LOSING CRITICAL MISMATCHES.

==================================================
PART 15 — RECOMMENDATION PRIORITY
==================================================

Rank recommendations:

P0 — Critical
P1 — High
P2 — Medium
P3 — Optional

Prioritize changes that reduce dashboard noise without weakening detection of serious MCAT/product mismatches.

==================================================
PART 16 — FINAL OUTPUT
==================================================

Create ONLY:

optimization.md

The document must contain:

1. Executive Summary
2. Current Architecture
3. Current Flagging Flow
4. Complete Flag Inventory
5. Title vs MCAT Findings
6. MCAT vs ISQ Findings
7. Title vs ISQ Findings
8. False Positive Sources
9. Severity Model Recommendation
10. Confidence Model Recommendation
11. Root-Cause Deduplication Recommendation
12. API Filtering Recommendation
13. N8N/Google Sheet Findings
14. Frontend Findings
15. Golden Dataset Recommendation
16. Prioritized Optimization Plan
17. Risks / Trade-offs
18. Recommended Validation Strategy
19. Exact Files/Functions That Would Need Changes Later
20. Final Recommended Target Architecture

CRITICAL:
This is a design/audit document, NOT an implementation task.

Do not modify any project file other than creating optimization.md.

Where documentation and actual code differ:
- trust the actual code
- clearly document the discrepancy
- do not silently correct the documentation

For every recommendation, clearly distinguish:
CURRENT BEHAVIOR
vs
RECOMMENDED FUTURE BEHAVIOR

Do not invent functionality that does not exist.

Use exact file paths, function names, class names, flag names, thresholds, and line numbers wherever they can be verified.

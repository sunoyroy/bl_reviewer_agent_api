# BL Reviewer Agent

Standalone LLM-only buy-lead reviewer for IndiaMART/SquadStack leads.
Reviews each lead's `title`, `mcat`, and ISQ answers for consistency and flags issues.

---

## Output Format

Every review returns:

```json
{
  "offer_id": "146420001285",
  "flags": ["title_mcat_mismatch"],
  "concise_reason": "Title describes BOPP sheets but mcat is Non Tearable Paper."
}
```

| Field | Type | Description |
|---|---|---|
| `offer_id` | string | Echoed from input |
| `flags` | list of strings | Flag names raised (empty = approved) |
| `concise_reason` | string | Short explanation, < 20 words |

### Flag Types

| Flag | Meaning |
|---|---|
| `title_mcat_mismatch` | Title and mcat do not describe the same product/category |
| `isq_filled_title_mismatch` | A filled ISQ answer conflicts with or is irrelevant to the title |
| `isq_filled_mcat_mismatch` | A filled ISQ answer conflicts with or is irrelevant to the mcat |

---

## Input Formats

Accepts both structured and CSV-style fields.

**Structured (preferred):**
```json
{
  "offer_id": "146420001285",
  "title": "BOPP Synthetic Non Tearable Sheets",
  "mcat": "Non Tearable Paper",
  "isq_filled": {
    "Printing Compatibility": "Offset",
    "Thickness": "200 micron"
  },
  "isq_asked": ["Printing Compatibility", "Thickness"]
}
```

**CSV-style (also accepted):**
```json
{
  "eto_ofr_display_id": "146420001285",
  "eto_ofr_title": "BOPP Synthetic Non Tearable Sheets",
  "glcat_mcat_name": "Non Tearable Paper",
  "attributes_combined": "Printing Compatibility: Offset; Thickness: 200 micron"
}
```

---

## Environment Variables

```powershell
$env:LLM_GATEWAY_API_KEY  = "your-api-key"              # Required
$env:LLM_GATEWAY_BASE_URL = "https://imllm.intermesh.net/v1"  # Default shown
$env:LLM_GATEWAY_MODEL    = "flex/openrouter/google/gemini-3-flash-preview"   # Default shown
```

---

## Option 1 — REST API (Production)

### Install & Start

```powershell
pip install fastapi uvicorn
uvicorn bl_reviewer_agent.api:app --host 0.0.0.0 --port 8000 --reload
```

### Endpoints

#### `GET /health` — Health check
```powershell
curl http://localhost:8000/health
```
```json
{"status": "ok", "model": "flex/openrouter/google/gemini-3-flash-preview", "base_url": "https://imllm.intermesh.net/v1"}
```

#### `POST /review` — Single lead
```powershell
curl -X POST http://localhost:8000/review `
  -H "Content-Type: application/json" `
  -d '{
    "eto_ofr_display_id": "146420001285",
    "eto_ofr_title": "BOPP Synthetic Non Tearable Sheets",
    "glcat_mcat_name": "Non Tearable Paper",
    "attributes_combined": "Printing Compatibility: Offset; Thickness: 200 micron"
  }'
```
```json
{
  "offer_id": "146420001285",
  "flags": [],
  "concise_reason": "Title, mcat, and ISQ attributes are consistent."
}
```

#### `POST /batch` — Multiple leads
```powershell
curl -X POST http://localhost:8000/batch `
  -H "Content-Type: application/json" `
  -d '{
    "leads": [
      {
        "eto_ofr_display_id": "111",
        "eto_ofr_title": "Cotton Yarn",
        "glcat_mcat_name": "Polyester Yarn"
      },
      {
        "eto_ofr_display_id": "222",
        "eto_ofr_title": "Steel Pipe",
        "glcat_mcat_name": "Steel Pipe"
      }
    ]
  }'
```
```json
{
  "results": [
    {"offer_id": "111", "flags": ["title_mcat_mismatch"], "concise_reason": "Cotton Yarn does not match Polyester Yarn mcat."},
    {"offer_id": "222", "flags": [], "concise_reason": "Title and mcat are consistent."}
  ]
}
```

### Interactive API Docs
Open **http://localhost:8000/docs** in a browser for the full Swagger UI.

---

## Option 2 — CLI (Single Lead)

```powershell
# From a file
python -m bl_reviewer_agent.cli --input bl_reviewer_agent\sample_payload.json

# Inline JSON
python -m bl_reviewer_agent.cli --json '{"eto_ofr_display_id":"111","eto_ofr_title":"Cotton Yarn","glcat_mcat_name":"Polyester Yarn"}'

# Pipe via stdin
cat payload.json | python -m bl_reviewer_agent.cli

# Save output to file
python -m bl_reviewer_agent.cli --input payload.json --output result.json
```

---

## Option 3 — Batch Runner (CSV / JSON file)

```powershell
# CSV input
python -m bl_reviewer_agent.batch_review --input "C:\path\to\offers.csv" --output-dir outputs\bl_reviewer_agent_batch

# JSON input
python -m bl_reviewer_agent.batch_review --input leads.json --output-dir outputs\bl_reviewer_agent_batch

# Multiple models
python -m bl_reviewer_agent.batch_review --input leads.json --models flex/openrouter/google/gemini-3-flash-preview google/gemini-2.5-flash-lite
```

Outputs per model:
- `<model>_results.json` — full results
- `<model>_results.csv` — flat CSV with flag columns
- `combined_model_results.csv` — side-by-side comparison across models
- `summary.json` — counts and top flag types

The batch runner checkpoints after every batch and resumes automatically on re-run.

---

## Option 4 — Programmatic (Python)

```python
from bl_reviewer_agent.agent import build_bl_reviewer_agent
from bl_reviewer_agent.input_parser import parse_review_request

agent = build_bl_reviewer_agent(
    model="flex/openrouter/google/gemini-3-flash-preview",
    api_key="your-api-key",
    base_url="https://imllm.intermesh.net/v1",
)

payload = {
    "eto_ofr_display_id": "146420001285",
    "eto_ofr_title": "BOPP Synthetic Non Tearable Sheets",
    "glcat_mcat_name": "Non Tearable Paper",
    "attributes_combined": "Printing Compatibility: Offset; Thickness: 200 micron",
}
request = parse_review_request(payload)
result = agent.review(request)
# {"flags": [], "concise_reason": "..."}
```
## how to give input
```python
import requests
url = "http://localhost:8000/review"
payload = {
    "offer_id": "146420001285",
    "title": "BOPP Synthetic Non Tearable Sheets",
    "mcat": "Non Tearable Paper",
    "isq_filled": {
        "Printing Compatibility": "Offset",
        "Thickness": "200 micron"
    }
}
response = requests.post(url, json=payload)
print(response.json())
```
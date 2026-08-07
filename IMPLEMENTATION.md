# Buy Lead Reviewer Agent API - Implementation Documentation

## Overview
The **Buy Lead Reviewer Agent** is a full-stack system designed to review IndiaMART/SquadStack buy leads by analyzing relationships and consistency between product titles, categories (MCAT), and Interactive Search Queries (ISQ). The system is built with a highly optimized Python/FastAPI backend functioning as an AI agent, coupled with a React/Vite frontend for user interaction. 

It utilizes a **Hybrid Review Architecture**:
1. **BI Layer (Local Embedding):** Uses `fastembed` with a local sentence-transformer model (`paraphrase-multilingual-MiniLM-L12-v2`) to perform rapid cosine similarity checks. If the semantic match is high, the lead is approved immediately, saving costs and latency.
2. **LLM Layer (Generative AI):** If the BI Layer falls below a threshold, the system queries an external OpenAI-compatible LLM Gateway (e.g., using `gemini-3-flash-preview`) to perform nuanced comparisons of the lead attributes, producing a structured JSON output with specific flags and reasons.

---

## Backend Implementation

The backend is built with **FastAPI** and is highly optimized for stateless, serverless environments like Vercel (using `/tmp` directories for AI model caching).

### Core Components

#### 1. `agent.py` (The Brain)
Defines the core agents handling the review logic:
- `LocalEmbeddingEngine`: Uses `fastembed` to compute cosine similarity between the lead `title` and `mcat`.
- `OpenAICompatibleBLReviewerAgent`: Handles direct HTTP communication with an LLM Gateway to request deep comparisons. 
- `HybridBLReviewerAgent`: The orchestrator that integrates both. It computes similarity first. If `similarity >= threshold` (e.g., 0.45/0.60), it returns a fast approval. Otherwise, it delegates to the LLM.
- *Note:* It forces caching to `/tmp` via `os.environ` to circumvent read-only filesystem issues in serverless platforms.

#### 2. `api.py` (The API Layer)
A FastAPI application exposing the agent functionality over HTTP:
- Implements a **Global Singleton Cache** for the agent to avoid reloading embedding models on every serverless cold start.
- `POST /review`: Accepts a single lead payload (validated via Pydantic models `N8nReviewPayload`) and returns a structured `ReviewResult`.
- `POST /batch`: Accepts an array of leads, processes them sequentially, and catches individual failures without breaking the entire batch.
- Includes bulletproof global exception handlers.

#### 3. `prompt.py` (The Prompting Engine)
Contains the highly specific system prompts governing the LLM's behavior:
- Instructs the LLM to compare `title` vs `mcat`, `mcat` vs `isq_filled`, and `isq_keys` vs `isq_asked`.
- Enforces strict flagging schemas (e.g., `title_mcat_mismatch`, `isq_filled_title_mismatch`).
- Requires output in a strictly formatted JSON object.

#### 4. `input_parser.py` (Data Normalization)
Since incoming lead data can take various shapes depending on the pipeline (N8N, CSV, direct JSON), this module robustly coerces inputs.
- Extracts `title`, `mcat`, `isq_filled`, and `isq_asked` from varying JSON key aliases.
- Handles stringified JSON, Python AST strings, and semicolon-delimited attribute pairs, parsing them into reliable Python dictionaries.

#### 5. `batch_review.py` & `cli.py` (Tooling)
- **`batch_review.py`**: A powerful offline script for batch processing large datasets. It features automatic retries (with backoff), checkpointing (to resume interrupted runs), and output generation (CSV and JSON summaries).
- **`cli.py`**: A command-line interface for running single payload reviews, excellent for debugging and CI/CD pipelines.

---

## Frontend Implementation

The frontend is located in the `frontend/` directory and is built using modern web development standards:
- **Framework:** React 18 with TypeScript.
- **Build Tool:** Vite, configured for blazing fast HMR and optimized builds (`vite.config.ts`).
- **Styling:** Tailwind CSS (`tailwind.config.js`, `postcss.config.js`) for utility-first styling, providing a responsive and modern UI out of the box.
- **Structure:** 
  - `src/components/`: Reusable UI components.
  - `src/services/`: API client utilities linking the frontend to the FastAPI backend.
  - `src/types.ts`: TypeScript interfaces ensuring type safety aligned with the backend's Pydantic models.

---

## Data Flow & Storage (Sheets/CSV)

The API is strictly stateless and does not contain a database. However, data persistence and "sheet" storage occur downstream through three distinct flows:

1. **N8N Google Sheets Automation (Primary):** The API is designed to be called by an N8N workflow (as seen in `Docs/Auditor (2).json`). N8N reads raw leads, sends them to this API (which expects an `N8nReviewPayload`), parses the JSON review results, and subsequently uses the `n8n-nodes-base.googleSheets` node to **append or update rows directly in a Google Sheet**.
2. **Offline Batch CSV:** For massive bulk reviews, `batch_review.py` processes JSON/CSV payloads and outputs the LLM reviews directly into local `.csv` files (e.g., `combined_model_results.csv`) via the standard Python `csv.DictWriter`.
3. **Frontend Export:** The Vite React frontend allows users to manually upload CSVs, process them, and download the resulting reviews as a new `.csv` blob directly from the browser.

---

## Deployment & Vercel Hosting Configuration

The project is natively optimized for **Vercel** serverless hosting. The included `vercel.json` uses the `@vercel/python` runtime to route all incoming traffic directly to `api.py`.

### How to Host this API Live on Vercel:

**Method 1: via GitHub (Recommended)**
1. Ensure your repository is pushed to GitHub (e.g., `https://github.com/sunoyroy/bl_reviewer_agent_api`).
2. Log into the [Vercel Dashboard](https://vercel.com/) and click **Add New... > Project**.
3. Import your GitHub repository.
4. **Crucial Step:** Before clicking deploy, expand the **Environment Variables** section and add:
   - `LLM_GATEWAY_API_KEY` (Your Gemini or Gateway API Key)
   - `LLM_GATEWAY_BASE_URL` (Optional if using Gemini directly: `https://generativelanguage.googleapis.com/v1beta/openai/`)
   - `LLM_GATEWAY_MODEL` (e.g., `gemini-1.5-flash`)
5. Click **Deploy**. Vercel will automatically read `vercel.json`, install `requirements.txt`, and expose your API on a live URL.

**Method 2: via Vercel CLI**
1. Install the CLI via npm: `npm i -g vercel`
2. Run `vercel login` to authenticate in your terminal.
3. Navigate to the project root in your terminal and run the command: `vercel`
4. Follow the prompts. Once deployed, run `vercel env add` to add your LLM API keys to the production environment, then run `vercel --prod` to push it live.

*Note on Vercel Constraints:* The backend explicitly forces `HF_HOME`, `FASTEMBED_CACHE_PATH`, and `TRANSFORMERS_CACHE` to the `/tmp` directory because Vercel's serverless filesystem is completely read-only except for the `/tmp` folder.

# Condition Briefing Generator (Demo)

Generates a structured strategy briefing for a medical condition using four CrewAI agents on OpenRouter,
running in parallel, each grounded in a free public API and each returning schema-validated JSON:

| Agent | Section | Tool (plain Python function) | Public API |
|---|---|---|---|
| 0 | Condition overview | `search_condition_reviews` | PubMed E-utilities (epidemiology / burden reviews, last 5 years) |
| 1 | Current standard of care | `search_guidelines` | PubMed E-utilities (practice guidelines, last 5 years) |
| 2 | Emerging treatments | `search_clinical_trials` | ClinicalTrials.gov v2 (active phase 2/3 interventional trials) |
| 3 | Key companies & institutions | `search_trial_sponsors` | ClinicalTrials.gov v2 (lead sponsors + collaborators, aggregated) |

## Architecture

```
 Browser ── http://localhost:3000
    │
┌───┼─────────────────────────── docker-compose ────────────────────────────────┐
│   ▼                                                                           │
│ frontend (nginx)                          backend (FastAPI, python:3.11)      │
│  React SPA  ──── /api/* proxy (300s) ───▶  POST /api/briefing {condition}     │
│                                            GET  /api/health                   │
│                                              │ run_briefing()                 │
│                                              ▼                                │
│  4 single-agent crews run in parallel (ThreadPoolExecutor)                    │
│  LLM: openrouter/anthropic/claude-haiku-4.5 (one instance per agent)          │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  │0 Overview       │ │1 Standard of    │ │2 Emerging       │ │3 Companies &    │
│  │ search_condition│ │  Care           │ │  Treatments     │ │  Institutions   │
│  │  _reviews       │ │ search_         │ │ search_clinical │ │ search_trial_   │
│  │  → PubMed       │ │  guidelines     │ │  _trials        │ │  sponsors       │
│  │                 │ │  → PubMed       │ │  → CT.gov       │ │  → CT.gov       │
│  └───────┬─────────┘ └───────┬─────────┘ └───────┬─────────┘ └───────┬─────────┘
│          │ pubmed            │ pubmed            │ trial             │ sponsor   │
│          ▼                   ▼                   ▼                   ▼           │
│   per-request SourceCollector: every record a tool returned → sources[]       │
│            ▼                                                                  │
│   BriefingResponse { condition_overview, standard_of_care, emerging_treatments,│
│                      companies_institutions, sources[], model, ... }          │
└───────────────────────────────────────────────────────────────────────────────┘
```

`sources` holds exactly what each agent's tool returned. The UI lists them once, deduplicated, in a Sources
section at the bottom (tagged with the sections that used each one), and the eval uses them to verify every
cited PMID, NCT ID, and sponsor trial count.

## Run locally

1. Put your OpenRouter key in `backend/.env` (template: `backend/.env.example`):
   ```bash
   OPENROUTER_API_KEY=sk-or-v1-...
   ```
2. Start everything:
   ```bash
   docker compose up --build
   ```
3. Open http://localhost:3000. A briefing takes about 20–30 seconds.

API only: `curl -X POST localhost:8000/api/briefing -H 'Content-Type: application/json' -d '{"condition":"Multiple Sclerosis"}'`.
Interactive API docs: http://localhost:8000/docs.

## Eval

Assertion-based checks over fixed test conditions (`backend/eval/cases.py`). It runs the real pipeline, so it
costs LLM calls (~25 seconds per case).

```bash
docker compose run --rm -T backend python -m eval.run_eval                  # all cases
docker compose run --rm -T backend python -m eval.run_eval --case sclerosis # one case
# re-check saved briefings without calling the LLM (handy when changing checks):
docker compose run --rm -T backend python -m eval.run_eval --from-dir eval/results/<timestamp>
```

| Check | Severity |
|---|---|
| All sections populated (summaries ≥150 chars, ≥1 key fact / therapy / company / institution) | FAIL |
| No refusal or error text | FAIL |
| Every agent called its tool (≥1 source recorded for each of the 4 agents) | FAIL |
| Every cited PMID (overview key facts, guidelines) was returned by that agent's own PubMed tool | FAIL |
| Every NCT ID anywhere in the briefing was returned by a ClinicalTrials.gov tool | FAIL |
| Organizations claiming a trial count appear in the sponsor tool results | FAIL |
| ≥1 organization matches a tool-returned sponsor | FAIL |
| Standard of care mentions an expected keyword for the case (e.g. metformin) | FAIL |
| ≥1 overview fact cites a PMID; every overview fact contains a number; ≥1 guideline cited; each therapy has an NCT ID; ≥3 sponsors matched; counts match; latency <300s | WARN |

Briefings and `report.json` are written to `backend/eval/results/<timestamp>/`. Exit code is 1 on any FAIL.

## Configuration (`backend/.env`)

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | — (required) | OpenRouter key |
| `OPENROUTER_MODEL` | `anthropic/claude-haiku-4.5` | Any OpenRouter slug with tool-calling + structured-output support. `anthropic/claude-sonnet-5` gives richer output but took ~165s sequentially vs ~25s for Haiku in parallel |
| `NCBI_API_KEY` | empty | Optional; raises PubMed limit from 3 to 10 req/s |
| `AGENT_MAX_ITER` | `6` | Max reasoning/tool iterations per agent |

## Develop without Docker

```bash
cd backend && python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
set -a && source .env && set +a
uvicorn app.main:app --reload --port 8000

cd frontend && npm install && npm run dev   # http://localhost:5173, proxies /api to :8000
```

## AWS ECS (not built yet)

Scope is local Docker Compose for now. Both images are stateless and env-configured, so an ECS Fargate
deployment needs: ECR repos, one ECS service per image, an ALB routing `/api/*` to the backend (idle timeout
≥300s) and `/*` to the frontend, and `OPENROUTER_API_KEY` from Secrets Manager.

## Limitations

- Synchronous request: the POST blocks for the whole crew run. Fine for a demo; a job queue + polling would
  be the production shape.
- No auth or persistence; each briefing is generated fresh.
- AI-generated content for strategy discussion, not clinical advice.

# ce-workflow

Multi-agent QA/QC workflow for cold electronics detector components.
A LangGraph pipeline (Monitor → DAQ → QC Analysis → Diagnostic → Catalog) acquires
ADC waveforms, flags per-channel anomalies, retrieves grounding context from a
local RAG knowledge base, and writes a markdown report — all streamed live to
the operator UI.

## Stack

- **Backend** — FastAPI, LangGraph, Qdrant (hybrid dense + sparse RAG), Ollama (local LLM + embeddings), HDF5 waveform storage
- **Frontend** — Vue 3 + Vuetify, Vite

## Quickstart

Prerequisites: Docker, [uv](https://docs.astral.sh/uv/), [Ollama](https://ollama.com), Node 20+.

```bash
# 1. Vector DB
cd docker && docker compose up -d        # Qdrant on :6333

# 2. Local models (one-time)
ollama pull qwen3.5:4b
ollama pull nomic-embed-text:v1.5

# 3. Backend
cd ../backend
cp .env.example .env
uv sync
uv run uvicorn main:app                  # http://localhost:8000

# 4. Frontend (separate terminal)
cd ../frontend
npm install
npm run dev                              # http://localhost:5173
```

Open the UI, upload a document via the left panel (a sample is at
`backend/seeds/dune_ce_intro.txt`), then click **QC Start** to run the pipeline.

## Tests

```bash
cd backend && uv run pytest              # Qdrant + Ollama required for integration tests
cd frontend && npm test
```

## More

- `backend/README.md` — detailed backend setup, dev auto-reload, seeding
- `backend/CONTEXT.md` — agent pipeline, SSE event schema, key files
- `frontend/CONTEXT.md` — Vue component map, shared state, SSE consumer
- `CONTEXT-MAP.md` — domain entry point
- Issue tracker — GitHub Issues on `czczc/ce-workflow`

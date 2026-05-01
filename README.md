# ce-workflow

QA/QC multi-agent workflow system for cold electronics detector components.

## Stack

- **Backend** — Python, LangGraph (agent orchestration), Qdrant (vector DB), Ollama (local LLM/embeddings)
- **Frontend** — Vue 3

## Backend

```bash
cd backend
uv sync
uv run pytest
```

Requires Qdrant and Ollama running locally (see `docker/`).

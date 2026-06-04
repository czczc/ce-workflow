## Agent skills

### Backlog

Issues live in GitHub Issues (`czczc/ce-workflow`). See `docs/agents/backlog.md`.

### Triage labels

Default label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Multi-context: `CONTEXT-MAP.md` at root points to `frontend/CONTEXT.md` (Vue 3) and `backend/CONTEXT.md` (LangGraph + Qdrant). See `docs/agents/domain.md`.

### Diagnosis

Detailed QC-failure diagnosis lives in the cets repo (`~/Code/cets`, `BNLIF/cets`) via its `/ce-diagnose` skill — open Claude Code there. This repo's monitor keeps the Ollama-based live diagnostics.

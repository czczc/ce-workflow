# CE-Workflow: Weekly Progress Report
**Week of May 4 – May 10, 2026**

---

## Executive Summary

A consolidation week between the v1 pipeline (W18) and the live `/monitor` page (W20). The work split into three threads running in parallel: **(1) a refactor sweep** that broke up the monolithic agent modules and extracted reusable SSE / RAG / chat primitives; **(2) a CE_Agent data-format alignment** that introduced a real LArASIC parameter schema and a CETS chip-traceability link in QC reports; and **(3) a six-phase UI redesign** that replaced VueFlow with a hand-rolled SVG pipeline graph and applied a unified design-token / dark-theme pass across every page.

**19 issues closed (#37–#57, minus #45/#46). ~3,600 insertions / ~960 deletions across 69 files** — note the high deletion count reflects the refactor + UI rewrite, not just additions.

---

## What Was Built

### Phase 1 — Refactor Sweep (May 4): Break Up Monoliths

| Issue | Deliverable |
|-------|-------------|
| #37 | Extract `RetrievedChunk` dataclass from `rag_pipeline.py` so SSE producers, the reranker, and the frontend all speak one shape |
| #38 | Extract backend SSE helper module (`sse.py`) — `event()` serializer, `[DONE]` sentinel, `ollama_tokens()` async generator |
| #39 | Extract frontend `useStream.js` SSE composable — the fetch → ReadableStream → dispatch loop, used by `ChatView` and `QcStartButton` |
| #40 | Extract `RunStore` from `catalog_agent.py`; fix silent MCP errors that were swallowing tool-dispatch failures |
| #41 | Refactor `useChat.js` from module-level singleton into a factory composable (unblocks per-page chat instances) |
| #42 | Narrow `PipelineState` into per-node `TypedDict`s so each agent declares the slice of state it reads/writes |

**Result:** The pieces the W20 `/monitor` work depended on — `useStream`, `sse.py`, `RunStore` — landed first, in their own modules, with tests.

---

### Phase 2 — CE_Agent Data-Format Alignment (May 5)

| Issue | Deliverable |
|-------|-------------|
| #43 | CE_Agent-format mock data factory — mock fixtures now match the on-bench DAQ shape |
| #44 | `LArASIC` parameter schema (`femb_test_schema.py`, 301 lines) + `take_data` MCP tool — typed parameter map for the front-end ASIC |
| #47 | Diagnostic pipeline updated to CE_Agent format *(closed as duplicate — folded into #44)* |
| #48 | Show `femb_serial` and `config_label` in the reports list table |
| #49 | Integrate CETS chip traceability — QC report links out to the CETS chip-detail page for each FEMB |

**Result:** Reports now carry real component provenance (FEMB serial → CETS chip lookup), and the agent pipeline speaks the same parameter vocabulary as the bench DAQ.

---

### Phase 3 — UI Redesign, 6 Phases (May 5–6)

| Issue | Phase | Deliverable |
|-------|-------|-------------|
| #50 | 1 | Design tokens, Vuetify light theme, fonts (Inter + JetBrains Mono) |
| #51 | 2 | App shell — 48px topbar, 24px statusbar, 3-column grid |
| #52 | 3 | Left rail — `QcStartButton` restyle + **pure-SVG `PipelineGraph` replaces VueFlow** |
| #53 | 4 | Center — `ChatView.vue` full restyle (markdown, auto-scroll, composer) |
| #54 | 5 | Right rail — `TelemetryRail.vue` + `Sparkline.vue` |
| #55 | 6 | Token pass for Reports, Documents, Upload pages |
| `68164d8` | — | Dark theme toggle |

**Result:** A unified design language across every page, with the heavyweight VueFlow+dagre dependency replaced by a 280×480 hand-coded SVG.

---

### Phase 4 — Dev Ergonomics (May 6–7)

| Issue | Deliverable |
|-------|-------------|
| #56 | Replace `status.sh` with `scripts/manage.sh` — multi-service `start/stop/restart/logs`; port-based process discovery (no PID files) |
| #57 | Model switcher + RAG parameter tuning in the chat UI (`reasoning_model`, `retrieval_top_k`, `generation_top_k`, `reranker_enabled`) |
| `f5f976c` | — | Composer prompt history (↑/↓ recall) |

**Result:** One command to bring the stack up/down/inspect logs; operators can swap models and tune RAG knobs from the UI without restarting.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Browser (Vue 3 + Vuetify 3, design-token theme, light/dark)                 │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  App shell (topbar / 3-col grid / statusbar)                         │   │
│  │  ┌────────────┐  ┌──────────────────┐  ┌────────────────────┐        │   │
│  │  │ Left rail  │  │ Center           │  │ Right rail         │        │   │
│  │  │ QcStart +  │  │ ChatView         │  │ TelemetryRail      │        │   │
│  │  │ SVG        │  │ (markdown,       │  │ + Sparkline        │        │   │
│  │  │ Pipeline   │  │ history, model   │  │ (recent runs,      │        │   │
│  │  │ Graph      │  │ switcher #57)    │  │ retrieval ctx)     │        │   │
│  │  └────────────┘  └────────┬─────────┘  └────────────────────┘        │   │
│  │                           │                                          │   │
│  │       composables/  useStream.js (#39)   useChat.js factory (#41)    │   │
│  └───────────────────────────┼──────────────────────────────────────────┘   │
└──────────────────────────────┼──────────────────────────────────────────────┘
                               │  SSE / JSON
┌──────────────────────────────▼──────────────────────────────────────────────┐
│  FastAPI backend                                                             │
│   sse.py (#38)   RetrievedChunk (#37)   per-node PipelineState (#42)        │
│      │                  │                       │                            │
│      ▼                  ▼                       ▼                            │
│   pipeline.py  →  rag_pipeline.py  →  diagnostic_agent.py  →  catalog_agent  │
│                                                                ↓             │
│                                                          RunStore (#40)      │
│                                                                ↓             │
│                                                       SQLite (qc.db)         │
│   femb_test_schema.py (#44, LArASIC params)                                  │
│   MCP: take_data + CETS chip lookup (#44, #49)                               │
└──────────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
                  scripts/manage.sh (#56) — start/stop/restart/logs by port
```

---

## Key Technical Decisions

### Drop VueFlow for a 280×480 hand-coded SVG

`PipelineGraph.vue` (#52) renders 8 nodes + bezier edges directly in SVG, driven by `activeNode` + `completedNodes` refs from `useChat.js`.

- **Why it matters:** VueFlow + dagre brought in a layout engine and a node-renderer abstraction we weren't using; the pipeline has fixed topology.
- **Concrete benefit:** removed a heavyweight dep; the pulsing-ring active animation and checkmark-on-completion are CSS + one SVG `<circle>` each.

### Per-node `TypedDict`s instead of one fat `PipelineState`

#42 split the LangGraph state into the slice each node actually reads/writes.

- **Why it matters:** the old `PipelineState` let any node touch any field; refactor-time blast radius was the whole graph.
- **Concrete benefit:** the W20 monitor session work could add new state shapes without touching `pipeline.py`.

### Extract before reuse

The `sse.py` / `useStream.js` / `RunStore` / `RetrievedChunk` extractions (#37–#40) preceded any feature that needed them.

- **Why it matters:** `/monitor` (W20) consumed all four — extracting them as part of the feature would have mixed refactor noise into feature PRs.
- **Concrete benefit:** W20's PRs are mostly additive; the deletions in those diffs are limited to what each feature actually replaces.

### `useChat.js` factory > module-level singleton

#41 — `useChat()` now returns a per-instance set of refs.

- **Why it matters:** `/monitor` needs its own chat thread (session-scoped, separate from the global QC chat).
- **Concrete benefit:** `MonitorChat.vue` in W20 reuses 100% of the chat composable; the only difference is which factory call it consumes.

### `LArASIC` is a typed schema, not a dict

`femb_test_schema.py` (#44, 301 lines) defines the parameter map as Pydantic models with explicit ranges/units.

- **Why it matters:** the diagnostic agent and the CETS chip lookup both consume these values; "stringly typed" would have meant runtime crashes deep inside the LLM call path.
- **Concrete benefit:** the `take_data` MCP tool validates parameters before dispatch; CETS link generation is `model.dump()`-driven.

### Port-based process discovery in `manage.sh`

#56 replaced PID-file tracking with `lsof -i :PORT` lookups.

- **Why it matters:** PID files lie. A crashed process leaves a stale file; a manually-restarted one writes the wrong PID.
- **Concrete benefit:** `manage.sh status` is correct even after kernel-9 kills or shell-driven restarts.

---

## Metrics

| Metric | Value |
|---|---|
| Issues closed | 19 (#37–#57, excl. #45/#46) |
| Commits | 24 |
| Lines added / removed | 3,589 / 957 |
| Refactor PRs | 6 (#37–#42) |
| UI-redesign PRs | 6 (#50–#55) |
| Deps removed | VueFlow + dagre (replaced by hand-coded SVG) |
| New backend module | `sse.py`, `run_store.py`, `femb_test_schema.py` |
| New frontend composable | `useStream.js`, factored `useChat.js` |

---

## Current System Capabilities (end of W19)

1. One-command service lifecycle: `manage.sh start | stop | restart | status | logs`.
2. Operator can pick the reasoning model and tune RAG knobs (top-k RRF, top-k Rerank, reranker on/off) live from the chat composer.
3. Light/dark theme with a single design-token source of truth.
4. Pipeline visualization is a self-contained SVG component — no graph-library dependency.
5. Reports table shows `femb_serial` and `config_label`; each row links out to the matching CETS chip-detail page.
6. Mock data factory and DAQ now speak the CE_Agent format; the `take_data` MCP tool dispatches with validated `LArASIC` parameters.
7. Composer keeps a prompt history (↑/↓ recall).
8. Backend SSE plumbing, frontend SSE consumer, run persistence, and the retrieved-chunk dataclass all live in single-purpose modules.

---

## Open / Next (going into W20)

- Mock-only data path — no on-bench DAQ source yet (addressed in W20 by `/monitor` + SSH rsync).
- `useChat.js` is a factory but there is still only one consumer in W19; the factory's value is unlocked in W20 by `MonitorChat`.
- CETS link is a deep-link only; no inline preview of chip history.
- `manage.sh` discovers by port but doesn't gate on health-check before reporting "started."

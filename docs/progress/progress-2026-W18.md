# CE-Workflow: Weekly Progress Report
**Week of Apr 29 – May 3, 2026**

---

## Executive Summary

Built a full-stack, multi-agent QA/QC workflow system for cold electronics (CE) detector components from scratch in one week. The system takes a detector component through a complete automated quality-control pipeline — from hardware gate check through waveform acquisition, anomaly analysis, and RAG-backed diagnosis — and produces a structured report, all visible to operators in real time through a streaming chat interface.

**36 issues closed. ~2,600 lines of production code shipped across backend and frontend.**

---

## What Was Built

### Phase 1 — Foundation (Apr 29–30): RAG Chat Interface

| Issue | Deliverable |
|-------|-------------|
| #2 | Repo scaffold: `backend/` Python, `frontend/` Vue 3 |
| #3 | Pydantic Settings config module — all service URLs and model names via `.env` |
| #4 | Embedding service — Ollama `nomic-embed-text` wrapper with integration tests |
| #5 | Document store — Qdrant upsert, BM25, hybrid dense+sparse search with RRF fusion |
| #6 | RAG pipeline — ingest and query orchestration with integration tests |
| #7 | FastAPI chat API — SSE streaming, file upload, document list endpoints |
| #8 | Vue frontend — ChatView, UploadPanel, QcStartButton wired to backend |
| #9 | End-to-end demo — seed knowledge base, upload → ask → RAG-grounded answer |
| #10 | Monitor agent — hardware gate with placeholder tool calls |
| #16 | RAG-only constraint — system prompt refuses off-topic questions |
| #17 | Retrieval SSE event — backend streams chunk metadata |
| #18 | Retrieval debug panel — collapsible in-chat view of retrieved chunks with scores |
| #19 | Retrieval tuning — `top_k=10`, removed over-aggressive `min_score` RRF filter |

**Result:** A working RAG chat assistant over CE technical documentation.

---

### Phase 2 — Agent Pipeline (Apr 30 – May 1): LangGraph QC Agents

| Issue | Deliverable |
|-------|-------------|
| #24 | Migrate agent orchestration to LangGraph (`StateGraph`) |
| #21/#25 | DAQ Agent — 32-channel ADC waveform generation + HDF5 persistence in `data/` |
| #22 | QC Analysis Agent — per-channel anomaly detection (baseline drift, high noise, stuck bit, shape anomaly) |
| #23 | Diagnostic Agent — maps anomaly types → suggested actions |
| #12 | Catalog & Report Agent — writes run + markdown summary to `qc.db` (SQLite) |
| #29 | Unified pipeline — all agents compiled into a single `StateGraph` in `pipeline.py` |
| #30 | Cross-encoder reranking — optional reranker pass on RAG results before generation |

**Result:** End-to-end QC pipeline running as a single compiled LangGraph graph.

---

### Phase 3 — Integration & UI Polish (May 1–3): Full System

| Issue | Deliverable |
|-------|-------------|
| #26 | Multi-turn chat history — last 6 turns included in LLM context |
| #31 | Vue Router + page restructure — Chat, Documents, Reports pages |
| #32 | Backend SSE `node_active` / `node_done` events emitted from pipeline |
| #33 | Agent graph visualization — live animated pipeline flowchart in chat left panel |
| #34 | Split QC Start buttons — **QC Start** (clean run) vs **QC Start (Test)** (anomaly injection) |
| #35 | Reports page — paginated table view, server-side pagination, detail page |
| #15 | Django QC DB MCP server — read-only `cets.sqlite3` access via MCP (`list_fembs`, `get_femb`) |
| #36 | MCP tool calling in chat — LLM can call `list_fembs`/`get_femb` mid-conversation |

**Result:** Fully integrated system with live pipeline visualization, component provenance lookup, and a complete reports library.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│  Browser (Vue 3 + Vuetify 3 + Vite)                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐  ┌───────────┐  │
│  │  ChatPage   │  │  GraphFlow   │  │ DocumentsPage│  │ReportsPage│  │
│  │  ChatView   │  │  (VueFlow +  │  │  UploadPanel │  │+ Detail   │  │
│  │useChat.js   │  │  dagre layout│  │              │  │           │  │
│  └──────┬──────┘  └──────────────┘  └──────┬───────┘  └─────┬─────┘  │
│         │  SSE (text/event-stream)          │ multipart       │ JSON   │
└─────────┼─────────────────────────────────┼─────────────────┼────────┘
          │                                 │                 │
┌─────────┼─────────────────────────────────┼─────────────────┼────────┐
│  FastAPI + Uvicorn (backend/main.py)       │                 │        │
│  POST /chat/stream   POST /qc/start[?test] │ POST /documents/upload   │
│         │                                 │       GET /reports        │
│         ▼                                 ▼                 ▼        │
│  ┌─────────────────┐   ┌──────────────────────┐  ┌───────────────┐  │
│  │  RAG Chat       │   │  LangGraph Pipeline  │  │  catalog_agent│  │
│  │  (3-phase MCP   │   │  (pipeline.py)       │  │  (SQLite)     │  │
│  │   tool calling) │   │                      │  └───────────────┘  │
│  └────────┬────────┘   │  check_hardware      │                      │
│           │            │       ↓              │                      │
│           │            │  monitor_respond     │                      │
│           │            │       ↓ (if "good")  │                      │
│           │            │  daq_acquire (HDF5)  │                      │
│           │            │       ↓              │                      │
│           │            │  qc_analyze          │                      │
│           │            │       ↓ (if anomaly) │                      │
│           │            │  retrieve_context    │                      │
│           │            │       ↓              │                      │
│           │            │  build_diagnosis     │                      │
│           │            │       ↓              │                      │
│           │            │  narrate (LLM)       │                      │
│           │            │       ↓              │                      │
│           │            │  catalog_write       │                      │
│           │            └──────────────────────┘                      │
└───────────┼───────────────────────────────────────────────────────────┘
            │
     ┌──────┼──────────────────────────────────────┐
     │      │  External Services                   │
     │  ┌───▼──────┐  ┌──────────┐  ┌───────────┐  │
     │  │  Ollama  │  │  Qdrant  │  │ Django DB │  │
     │  │  (local  │  │  (vector │  │ MCP Server│  │
     │  │   LLM +  │  │   DB)    │  │ :8001/mcp │  │
     │  │  embed)  │  │          │  └───────────┘  │
     │  └──────────┘  └──────────┘                 │
     └─────────────────────────────────────────────┘
```

---

## Key Technical Decisions and Their Rationale

### 1. LangGraph for Agent Orchestration

**Decision:** Use LangGraph `StateGraph` as the agent runtime instead of custom async state machines or a simpler sequential chain.

**Why it matters:** LangGraph's typed `TypedDict` state ensures every node sees the same schema — no hidden globals or argument threading. Conditional edges (`_route_after_monitor`, `_route_after_qc`) make branching logic explicit and auditable in the graph definition, not scattered across business logic. The single compiled `graph` object in `pipeline.py` is the ground-truth description of the QC workflow.

**Concrete benefit:** Adding a new pipeline step is one `add_node` + `add_edge` call. The streaming mode (`graph.astream(..., stream_mode=["messages", "updates"])`) returns both token-level and node-level events from the same call, which powers the live UI without any extra plumbing.

---

### 2. Server-Sent Events (SSE) as the Universal Streaming Protocol

**Decision:** All long-running endpoints (`/chat/stream`, `/qc/start`) return `text/event-stream` with a typed JSON event schema (`token`, `tool_result`, `node_active`, `node_done`, `sources`, `retrieval`).

**Why it matters:** SSE is unidirectional HTTP — no WebSocket handshake, no connection state, browser-native. Every event type serves a different consumer: `token` events build the streaming chat bubble; `node_active`/`node_done` animate the GraphFlow visualization; `retrieval` populates the debug panel; `tool_result` logs tool execution. All consumers share a single fetch loop pattern in `useChat.js`.

**Concrete benefit:** The chat interface and the QC pipeline viewer are the same component stack. `ChatView` and `QcStartButton` share module-level singletons from `useChat.js` — neither knows about the other, but both write to the same message thread.

---

### 3. Hybrid Dense + Sparse Search with RRF Fusion

**Decision:** Maintain two Qdrant collections (`ce_dense` for semantic embeddings, `ce_sparse` for BM25 keyword search) and merge results using Reciprocal Rank Fusion.

**Why it matters:** Technical documentation for detector hardware contains both conceptual descriptions (benefiting semantic search) and precise terms like `COLDADC`, `FEMB`, `stuck_bit` (benefiting exact-match keyword search). Neither alone is sufficient. RRF fuses the ranked lists without requiring score normalization across different embedding spaces.

**Concrete benefit:** The retrieval debug panel exposes per-chunk `rrf_score`, `in_dense`, and `in_sparse` flags, making it possible to inspect which retrieval path contributed each chunk.

---

### 4. MCP (Model Context Protocol) as the External Database Interface

**Decision:** The Django QC database (`cets.sqlite3`) is exposed as a standalone MCP server (`mcp_django_db.py`) rather than importing it directly or calling a REST API.

**Why it matters:** MCP decouples the LLM from the data source's implementation. The chat endpoint discovers available tools (`list_fembs`, `get_femb`) at runtime; the LLM decides when and whether to call them. The pipeline's catalog agent calls the same MCP interface, so both conversational queries and automated QC runs share the same data access layer.

**Concrete benefit:** The 3-phase chat stream (generate → execute tools → generate again with results) is entirely driven by the LLM's tool-call decisions, not hardcoded branching. The MCP server fails gracefully — if unreachable, the pipeline logs a warning and continues without component history.

---

### 5. HDF5 for Waveform Storage

**Decision:** Each QC run writes 32-channel ADC waveform data to `data/{timestamp}/waveforms.h5` using HDF5 via `h5py`.

**Why it matters:** Raw waveform data is large, numerical, and hierarchical (one dataset per channel). HDF5 handles this natively — the QC analysis node reads only the channels it needs via key iteration without loading the entire file. The run directory path is propagated through `PipelineState.run_dir`, making the file location an explicit pipeline artifact rather than a convention.

---

### 6. Pydantic Settings for Configuration

**Decision:** All service URLs, model names, and tunable parameters (`top_k`, `history_turns`, `reranker_enabled`) live in a single `Settings` class backed by `.env`.

**Why it matters:** Every component in the system (embedding, Qdrant, Ollama, SQLite path, MCP URL) is configured from one place, with sensible defaults that make the system runnable out-of-the-box. Switching from `qwen3.5:4b` to a larger reasoning model or pointing to a remote Qdrant instance requires one `.env` change, not a code edit.

---

### 7. Vue 3 Composition API + Module-Level Singletons

**Decision:** Shared UI state (`messages`, `streaming`, `activeNode`, `completedNodes`) lives in `useChat.js` as module-level `ref` singletons, not as component props or Pinia store.

**Why it matters:** `ChatView` renders the message thread. `QcStartButton` appends QC pipeline output to the same thread. `GraphFlow` reads `activeNode` and `completedNodes` to animate the pipeline. All three are independent components on different parts of the page — they share state without a parent component threading props.

**Concrete benefit:** The graph visualization updates live as SSE events arrive in `QcStartButton`, without any direct coupling between those two components.

---

## Metrics

| Metric | Count |
|--------|-------|
| Issues closed | 36 |
| Commits | ~40 |
| Backend Python files | 12 |
| Frontend source files | 14 |
| Agent pipeline nodes | 8 |
| SSE event types | 7 |
| Integration test files | 4 |
| External service dependencies | 3 (Ollama, Qdrant, optional MCP) |

---

## Current System Capabilities

1. **Document ingestion** — Upload CE technical docs; chunked, embedded, indexed in Qdrant
2. **RAG chat** — Multi-turn Q&A grounded strictly in ingested documents, with retrieval debug panel
3. **MCP tool calling in chat** — LLM can look up FEMB component history from the Django DB mid-conversation
4. **QC pipeline** — Full automated run: hardware gate → DAQ → analysis → diagnosis → report
5. **Test mode** — "QC Start (Test)" injects 2–5 random waveform anomalies to exercise the full anomaly path
6. **Live pipeline visualization** — Animated node graph showing active/completed/pending states
7. **Reports library** — Paginated table of all QC runs with per-run detail pages

---

## Open / Next

- Component serial number input in the QC Start flow (so `catalog_write` always has a `component_id`)
- Real hardware anomaly detection endpoint (currently a random 20% failure placeholder)
- Persistent multi-turn history across page reloads
- Production deployment configuration (reverse proxy, non-local Ollama/Qdrant)

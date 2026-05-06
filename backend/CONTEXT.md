# Backend Context

## Stack

| Layer | Technology |
|---|---|
| API server | FastAPI + Uvicorn |
| Agent orchestration | LangGraph (`StateGraph`) |
| LLM inference | Ollama via `langchain-ollama` (`ChatOllama`) |
| Vector DB | Qdrant — hybrid dense + sparse (BM25) search |
| Waveform storage | HDF5 via `h5py` |
| Config | Pydantic Settings (`.env` → `config.py`) |

## Agent pipeline

```
POST /qc/start[?test=true]
      │
      ▼
Monitor Agent          checks hardware anomaly detection service
      │ status == "good"
      ▼
DAQ Agent              generates 32-ch ADC waveforms, saves to HDF5
                       inject_anomalies=True (test mode) or False (normal mode)
      │
      ▼
QC Analysis Agent      reads HDF5, detects baseline drift / high noise /
                       stuck bits / shape anomalies per channel
      │ n_anomalous > 0
      ▼
Retrieve Context       RAG query against ingested documents
      │
      ▼
Diagnostic Agent       maps anomaly types → suggested actions (RAG-backed)
      │
      ▼                (skipped if n_anomalous == 0)
Catalog & Report       writes run + summary to qc.db (SQLite), streams narrative
```

If Monitor Agent returns `status != "good"`, the pipeline stops and the operator is instructed to fix the defect before retrying.

`test=true` (QC Start (Test) button) injects 2–5 random anomalies into the waveforms. `test=false` (QC Start button) produces clean waveforms — QC always passes.

## LangGraph pattern

Each agent is a `StateGraph` with a `TypedDict` state. Nodes are `async` functions that receive state and return a partial update dict. The compiled graph is module-level; `run_<agent>()` is an `async` generator that calls `graph.astream(..., stream_mode=["messages", "updates"])` and bridges the events to SSE.

```python
class AgentState(TypedDict):
    some_field: dict
    response: str

async def my_node(state: AgentState) -> dict:
    ...
    return {"some_field": result}

builder = StateGraph(AgentState)
builder.add_node("my_node", my_node)
...
graph = builder.compile()

async def run_agent():
    async for mode, data in graph.astream({...}, stream_mode=["messages", "updates"]):
        if mode == "updates" and "my_node" in data:
            yield f"data: {json.dumps({'type': 'tool_result', ...})}\n\n"
        elif mode == "messages":
            msg, _ = data
            if msg.content:
                yield f"data: {json.dumps({'type': 'token', 'text': msg.content})}\n\n"
    yield "data: [DONE]\n\n"
```

## SSE event schema

All agent endpoints return `text/event-stream`. Each line is `data: <json>\n\n`.

| `type` | Fields | Consumer |
|---|---|---|
| `token` | `text: str` | Appended to current agent message bubble |
| `tool_result` | `tool: str`, `result: dict` | Logged / forwarded downstream |
| `loading` | — | Shows spinner |
| `sources` | `sources: str[]` | Displayed as source tags below message |
| `retrieval` | `chunks: Chunk[]` | Shown in collapsible Retrieval Context panel (TelemetryRail) |
| `node_active` | `node: str` | Highlights the named node in PipelineGraph |
| `node_done` | `node: str` | Marks node completed in PipelineGraph (checkmark) |
| `[DONE]` | (bare string, not JSON) | Ends the stream |

## Waveform storage

- Root: `backend/data/` (gitignored)
- Each QC run: `backend/data/{YYYYmmddTHHMMSS}/waveforms.h5`
- HDF5 layout: one dataset per channel, named `channel_00` … `channel_31`, each a 1-D int array of ADC samples
- Default: 32 channels × 2300 samples (configurable via `n_samples` param on `run_daq_agent`)
- The `daq_acquire` tool-result event includes `run_dir` (absolute path) so downstream agents know where to load the file

## Hardware check

- `GET {HARDWARE_CHECK_URL}` → `{"status": "good" | "defect detected", "detail": "..."}`
- Default URL: `http://127.0.0.1:8000/hardware/anomaly-check` (same FastAPI server, placeholder endpoint)
- Override via `HARDWARE_CHECK_URL` in `.env`

## Reports API

| Endpoint | Description |
|---|---|
| `GET /reports?page=1&limit=20` | Returns `{items: [...], total: N}` — server-side paginated |
| `GET /reports/{id}` | Single run record; 404 if not found |
| `GET /settings` | Returns runtime config: `reasoning_model`, `retrieval_top_k`, `generation_top_k`, `reranker_enabled` |

**Run record fields:** `id`, `run_dir`, `timestamp`, `passed`, `n_channels`, `n_anomalous`, `summary` (markdown)

SQLite DB path: `backend/data/qc.db` (configurable via `SQLITE_DB_PATH` in `.env`)

Tables: `qc_runs` (run metadata) and `reports` (markdown summary, FK to `qc_runs.id`).

## Key files

| File | Purpose |
|---|---|
| `main.py` | FastAPI app, all route definitions |
| `config.py` | Pydantic settings, all env vars |
| `pipeline.py` | Full LangGraph pipeline — `PipelineState`, all nodes, `run_pipeline(test)` SSE generator |
| `monitor_agent.py` | Hardware gate node |
| `daq_agent.py` | Waveform generation (`inject_anomalies` flag) + HDF5 persistence |
| `qc_analysis_agent.py` | Per-channel anomaly detection (baseline, noise, stuck bit, shape) |
| `diagnostic_agent.py` | Maps anomaly types → suggested actions |
| `catalog_agent.py` | SQLite writes (`list_reports`, `get_report`, `catalog_write`); MCP tool dispatch via `call_mcp_tool` |
| `sse.py` | SSE helpers: `event()` serializer, `DONE` sentinel, `ollama_tokens()` async generator |
| `document_store.py` | Qdrant hybrid search (dense + sparse) |
| `rag_pipeline.py` | Document ingestion and RAG query |
| `embedding.py` | Ollama embedding wrapper |

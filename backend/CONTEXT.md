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
POST /qc/start
      │
      ▼
Monitor Agent          checks hardware anomaly detection service
      │ status == "good"
      ▼
DAQ Agent              generates 32-ch ADC waveforms, saves to HDF5
      │
      ▼
QC Analysis Agent      (planned, #22) — reads HDF5, detects anomalies
      │
      ▼
Diagnostic Agent       (planned, #23) — diagnoses findings, RAG-backed
      │
      ▼
Catalog & Report Agent (planned, #12) — writes to qc.db, summarises run
```

If Monitor Agent returns `status != "good"`, the pipeline stops and the operator is instructed to fix the defect before retrying.

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
| `retrieval` | `chunks: Chunk[]` | Shown in collapsible debug panel |
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

## Key files

| File | Purpose |
|---|---|
| `main.py` | FastAPI app, route definitions, RAG chat endpoint |
| `config.py` | Pydantic settings, all env vars |
| `monitor_agent.py` | Monitor Agent — hardware gate, chains to DAQ on pass |
| `daq_agent.py` | DAQ Agent — waveform generation + HDF5 persistence |
| `document_store.py` | Qdrant hybrid search (dense + sparse) |
| `rag_pipeline.py` | Document ingestion and RAG query |
| `embedding.py` | Ollama embedding wrapper |

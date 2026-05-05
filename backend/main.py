import json
import random
import tempfile
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from sse import DONE, event, ollama_tokens
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from catalog_agent import call_mcp_tool, get_report, list_reports
from config import settings
from document_store import DocumentStore
from pipeline import run_pipeline
from rag_pipeline import ingest, query

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


_SYSTEM_PROMPT = (
    "You are a cold electronics QC assistant. "
    "Use the provided document context when relevant. "
    "Use the available tools to query the component database when asked about FEMBs, components, or test history. "
    "If neither context nor tools can answer, say so."
)

_CHAT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_fembs",
            "description": "List FEMBs from the component database, ordered by most recently updated.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of FEMBs to return (default 20).",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_femb",
            "description": "Return metadata and full test history for a FEMB by serial number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "serial_number": {
                        "type": "string",
                        "description": "FEMB serial number, e.g. '00030'.",
                    }
                },
                "required": ["serial_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_data",
            "description": (
                "Validate LArASIC DAQ parameters and return resolved register bits. "
                "Use when the user asks how to take data or configure a specific acquisition."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "slot": {"type": "integer", "description": "FEMB slot index (0–3)"},
                    "snc_label": {"type": "string", "description": "'200mV' or '900mV' baseline"},
                    "gain_label": {"type": "string", "description": "'4.7mV/fC', '7.8mV/fC', '14mV/fC', or '25mV/fC'"},
                    "peaking_label": {"type": "string", "description": "'0.5us', '1.0us', '2.0us', or '3.0us'"},
                    "num_samples": {"type": "integer", "description": "Number of samples (default 10)"},
                },
                "required": ["slot", "snc_label", "gain_label", "peaking_label"],
            },
        },
    },
]

_DAQ_TOOLS = {"take_data"}


async def _stream_chat(message: str, history: list[dict] = []):
    yield event({"type": "loading"})

    chunks = query(message, top_k=settings.retrieval_top_k)
    context = "\n\n".join(c.text for c in chunks)

    sources = sorted({c.source for c in chunks if c.source})
    if sources:
        yield event({"type": "sources", "sources": sources})

    if chunks:
        retrieval = [
            {
                "source": c.source,
                "chunk_index": c.chunk_index,
                "rrf_score": round(c.rrf_score, 4),
                "in_dense": c.in_dense,
                "in_sparse": c.in_sparse,
                "text": c.text,
            }
            for c in chunks
        ]
        yield event({"type": "retrieval", "chunks": retrieval})

    prior = history[-settings.history_turns :]
    user_content = f"Context:\n{context}\n\nQuestion: {message}" if context else message
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        *prior,
        {"role": "user", "content": user_content},
    ]

    ollama_url = f"{settings.ollama_base_url}/api/chat"

    async with httpx.AsyncClient(timeout=120.0) as client:
        # Phase 1: stream with tools — content tokens flow through; tool_calls are collected
        tool_calls = []
        async with client.stream(
            "POST",
            ollama_url,
            json={"model": settings.reasoning_model, "messages": messages, "tools": _CHAT_TOOLS, "stream": True, "think": False},
        ) as resp:
            resp.raise_for_status()
            async for content, calls in ollama_tokens(resp):
                if calls:
                    tool_calls = calls
                elif content:
                    yield event({"type": "token", "text": content})

        if not tool_calls:
            yield DONE
            return

        # Phase 2: execute each tool via MCP
        messages.append({"role": "assistant", "content": "", "tool_calls": tool_calls})
        for tc in tool_calls:
            name = tc["function"]["name"]
            args = tc["function"]["arguments"]
            if isinstance(args, str):
                args = json.loads(args)
            try:
                mcp_url = settings.daq_mcp_url if name in _DAQ_TOOLS else settings.django_mcp_url
                result = await call_mcp_tool(name, args, mcp_url)
                yield event({"type": "tool_result", "tool": name, "result": result or {}})
                messages.append({"role": "tool", "content": json.dumps(result)})
            except Exception as exc:
                msg = f"MCP tool '{name}' failed: {exc}"
                yield event({"type": "error", "message": msg})
                messages.append({"role": "tool", "content": json.dumps({"error": msg})})

        # Phase 3: stream final answer with tool results in context
        async with client.stream(
            "POST",
            ollama_url,
            json={"model": settings.reasoning_model, "messages": messages, "stream": True, "think": False},
        ) as resp:
            resp.raise_for_status()
            async for content, _ in ollama_tokens(resp):
                if content:
                    yield event({"type": "token", "text": content})

    yield DONE


@app.post("/chat/stream")
async def chat_stream(body: ChatRequest):
    return StreamingResponse(
        _stream_chat(body.message, body.history),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/hardware/anomaly-check")
async def hardware_anomaly_check():
    """Placeholder hardware anomaly detection service. Replace with real service URL via HARDWARE_CHECK_URL."""
    if random.random() < 0.2:
        return {"status": "defect detected", "detail": "Pin misalignment detected on COLDADC socket"}
    return {"status": "good", "detail": "No visual anomalies detected"}


@app.post("/qc/start")
async def qc_start(test: bool = Query(False), component_id: str = Query("")):
    return StreamingResponse(
        run_pipeline(test=test, component_id=component_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    chunk_size: int = Form(500),
    overlap: int = Form(50),
):
    suffix = Path(file.filename).suffix if file.filename else ""
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)

    try:
        doc_id = ingest(
            tmp_path,
            {"chunk_size": chunk_size, "overlap": overlap, "filename": file.filename},
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    return {"doc_id": doc_id}


@app.get("/reports")
async def get_reports(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100)):
    return list_reports(page=page, limit=limit)


@app.get("/reports/{report_id}")
async def get_report_detail(report_id: int):
    report = get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@app.get("/documents")
async def list_documents():
    store = DocumentStore()
    return store.list_documents()

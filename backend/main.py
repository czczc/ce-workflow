import json
import tempfile
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import settings
from document_store import DocumentStore
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


SYSTEM_PROMPT = (
    "Answer only using the provided context. "
    "If the answer isn't in the context, say so explicitly. "
    "Do not use outside knowledge."
)

NO_CONTEXT_REPLY = "I don't have any relevant documents to answer that question."


async def _stream_chat(message: str):
    yield f"data: {json.dumps({'type': 'loading'})}\n\n"

    chunks = query(message)
    context = "\n\n".join(c.text for c in chunks)

    sources = sorted({c.metadata.get("source", "") for c in chunks if c.metadata.get("source")})
    if sources:
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

    if chunks:
        retrieval = [
            {
                "source": c.metadata.get("source", ""),
                "chunk_index": c.metadata.get("chunk_index", 0),
                "rrf_score": round(c.metadata.get("_rrf_score", 0.0), 4),
                "in_dense": c.metadata.get("_in_dense", False),
                "in_sparse": c.metadata.get("_in_sparse", False),
                "text": c.text,
            }
            for c in chunks
        ]
        yield f"data: {json.dumps({'type': 'retrieval', 'chunks': retrieval})}\n\n"

    if not context:
        yield f"data: {json.dumps({'type': 'token', 'text': NO_CONTEXT_REPLY})}\n\n"
        yield "data: [DONE]\n\n"
        return

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {message}"},
    ]

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{settings.ollama_base_url}/api/chat",
            json={"model": settings.reasoning_model, "messages": messages, "stream": True, "think": False},
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)
                token = data.get("message", {}).get("content", "")
                if token:
                    yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"
                if data.get("done"):
                    break

    yield "data: [DONE]\n\n"


@app.post("/chat/stream")
async def chat_stream(body: ChatRequest):
    return StreamingResponse(
        _stream_chat(body.message),
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


@app.get("/documents")
async def list_documents():
    store = DocumentStore()
    return store.list_documents()

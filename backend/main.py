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


async def _stream_chat(message: str):
    yield f"data: {json.dumps({'type': 'loading'})}\n\n"

    chunks = query(message)
    context = "\n\n".join(c.text for c in chunks)
    prompt = f"Context:\n{context}\n\nQuestion: {message}" if context else message

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{settings.ollama_base_url}/api/generate",
            json={"model": settings.reasoning_model, "prompt": prompt, "stream": True},
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if data.get("response"):
                    yield f"data: {json.dumps({'type': 'token', 'text': data['response']})}\n\n"
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

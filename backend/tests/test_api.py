import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from rag_pipeline import RetrievedChunk
from main import app

client = TestClient(app)


# --- httpx streaming mocks ---

class _FakeOllamaResponse:
    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        yield '{"message": {"role": "assistant", "content": "hello"}, "done": false}'
        yield '{"message": {"role": "assistant", "content": " world"}, "done": true}'


class _FakeStream:
    async def __aenter__(self):
        return _FakeOllamaResponse()

    async def __aexit__(self, *_):
        pass


class _FakeHttpxClient:
    def stream(self, *_, **_kw):
        return _FakeStream()


class _FakeHttpxClientCtx:
    async def __aenter__(self):
        return _FakeHttpxClient()

    async def __aexit__(self, *_):
        pass


# --- tests ---

def test_chat_stream_no_context_still_calls_model():
    with (
        patch("main.query", return_value=[]),
        patch("httpx.AsyncClient", return_value=_FakeHttpxClientCtx()),
    ):
        resp = client.post("/chat/stream", json={"message": "what is cold electronics?"})

    assert resp.status_code == 200
    events = [line for line in resp.text.splitlines() if line.startswith("data:")]
    payloads = [e[len("data: "):] for e in events]

    assert json.loads(payloads[0]) == {"type": "loading"}
    assert json.loads(payloads[1]) == {"type": "token", "text": "hello"}
    assert json.loads(payloads[2]) == {"type": "token", "text": " world"}
    assert payloads[3] == "[DONE]"


def test_chat_stream_emits_loading_then_tokens():
    fake_chunk = RetrievedChunk(
        text="cold electronics use cryogenic detectors",
        source="detector.txt",
        chunk_index=0,
        rrf_score=0.016,
        in_dense=True,
        in_sparse=False,
    )
    with (
        patch("main.query", return_value=[fake_chunk]),
        patch("httpx.AsyncClient", return_value=_FakeHttpxClientCtx()),
    ):
        resp = client.post("/chat/stream", json={"message": "what is cold electronics?"})

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    events = [line for line in resp.text.splitlines() if line.startswith("data:")]
    payloads = [e[len("data: "):] for e in events]

    assert json.loads(payloads[0]) == {"type": "loading"}
    assert json.loads(payloads[1]) == {"type": "sources", "sources": ["detector.txt"]}

    retrieval = json.loads(payloads[2])
    assert retrieval["type"] == "retrieval"
    assert len(retrieval["chunks"]) == 1
    c = retrieval["chunks"][0]
    assert c["source"] == "detector.txt"
    assert c["chunk_index"] == 0
    assert c["rrf_score"] == 0.016
    assert c["in_dense"] is True
    assert c["in_sparse"] is False
    assert c["text"] == "cold electronics use cryogenic detectors"

    assert json.loads(payloads[3]) == {"type": "token", "text": "hello"}
    assert json.loads(payloads[4]) == {"type": "token", "text": " world"}
    assert payloads[5] == "[DONE]"


def test_upload_document_returns_doc_id(tmp_path):
    doc = tmp_path / "detector.txt"
    doc.write_text("cold electronics cryogenic detector content")

    with patch("main.ingest", return_value="abc-doc-id"):
        resp = client.post(
            "/documents/upload",
            files={"file": ("detector.txt", doc.read_bytes(), "text/plain")},
        )

    assert resp.status_code == 200
    assert resp.json() == {"doc_id": "abc-doc-id"}


def test_upload_passes_chunking_options(tmp_path):
    doc = tmp_path / "sample.txt"
    doc.write_text("some content")

    with patch("main.ingest", return_value="xyz") as mock_ingest:
        client.post(
            "/documents/upload",
            files={"file": ("sample.txt", doc.read_bytes(), "text/plain")},
            data={"chunk_size": "200", "overlap": "20"},
        )

    call_opts = mock_ingest.call_args[0][1]
    assert call_opts["chunk_size"] == 200
    assert call_opts["overlap"] == 20
    assert call_opts["filename"] == "sample.txt"


def test_list_documents_returns_docs():
    fake_docs = [
        {"id": "abc-123", "filename": "detector.txt", "ingested_at": "2026-04-29T00:00:00+00:00"},
        {"id": "def-456", "filename": "physics.txt", "ingested_at": "2026-04-29T01:00:00+00:00"},
    ]
    with patch("main.DocumentStore") as MockStore:
        MockStore.return_value.list_documents.return_value = fake_docs
        resp = client.get("/documents")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["id"] == "abc-123"
    assert data[0]["filename"] == "detector.txt"
    assert "ingested_at" in data[0]


def test_list_documents_empty():
    with patch("main.DocumentStore") as MockStore:
        MockStore.return_value.list_documents.return_value = []
        resp = client.get("/documents")

    assert resp.status_code == 200
    assert resp.json() == []

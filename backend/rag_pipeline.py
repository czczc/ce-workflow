import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from document_store import Chunk, DocumentStore
from embedding import embed


def _read_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return path.read_text(encoding="utf-8")


def _split_chunks(text: str, chunk_size: int, overlap: int) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = end - overlap
    return [c for c in chunks if c]


def ingest(file: str | Path, options: dict[str, Any] | None = None) -> str:
    path = Path(file)
    opts = options or {}
    chunk_size = opts.get("chunk_size", 500)
    overlap = opts.get("overlap", 50)

    text = _read_text(path)
    texts = _split_chunks(text, chunk_size, overlap)

    doc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(path.resolve())))
    ingested_at = datetime.now(timezone.utc).isoformat()
    store = DocumentStore()
    chunks = [
        Chunk(
            id=f"{doc_id}_{i}",
            text=t,
            vector=embed(t),
            metadata={
                "doc_id": doc_id,
                "source": opts.get("filename", path.name),
                "chunk_index": i,
                "ingested_at": ingested_at,
            },
        )
        for i, t in enumerate(texts)
    ]
    store.upsert(chunks)
    return doc_id


def query(text: str, top_k: int = 5, min_score: float = 0.02) -> list[Chunk]:
    vector = embed(text)
    store = DocumentStore()
    return store.hybrid_search(query_vector=vector, query_text=text, k=top_k, min_score=min_score)

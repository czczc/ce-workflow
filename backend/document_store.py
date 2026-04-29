import hashlib
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client import models

from config import settings

_VOCAB_SIZE = 2**16


@dataclass
class Chunk:
    id: str
    text: str
    vector: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))


def _sparse_vector(text: str) -> models.SparseVector:
    tokens = text.lower().split()
    if not tokens:
        return models.SparseVector(indices=[], values=[])
    counts = Counter(tokens)
    total = len(tokens)
    seen: dict[int, float] = {}
    for token, count in counts.items():
        idx = int(hashlib.blake2s(token.encode(), digest_size=4).hexdigest(), 16) % _VOCAB_SIZE
        seen[idx] = seen.get(idx, 0.0) + count / total
    return models.SparseVector(indices=list(seen.keys()), values=list(seen.values()))


class DocumentStore:
    def __init__(self):
        self.client = QdrantClient(url=settings.qdrant_url)

    def _ensure_collections(self, vector_size: int) -> None:
        existing = {c.name for c in self.client.get_collections().collections}

        if settings.dense_collection not in existing:
            self.client.create_collection(
                settings.dense_collection,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )

        if settings.sparse_collection not in existing:
            self.client.create_collection(
                settings.sparse_collection,
                vectors_config={},
                sparse_vectors_config={
                    "bm25": models.SparseVectorParams(
                        index=models.SparseIndexParams(on_disk=False)
                    )
                },
            )

    def upsert(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        self._ensure_collections(len(chunks[0].vector))

        self.client.upsert(
            settings.dense_collection,
            points=[
                models.PointStruct(
                    id=_point_id(chunk.id),
                    vector=chunk.vector,
                    payload={"_chunk_id": chunk.id, "text": chunk.text, **chunk.metadata},
                )
                for chunk in chunks
            ],
        )

        self.client.upsert(
            settings.sparse_collection,
            points=[
                models.PointStruct(
                    id=_point_id(chunk.id),
                    vector={"bm25": _sparse_vector(chunk.text)},
                    payload={"_chunk_id": chunk.id, "text": chunk.text, **chunk.metadata},
                )
                for chunk in chunks
            ],
        )

    def hybrid_search(
        self, query_vector: list[float], query_text: str, k: int
    ) -> list[Chunk]:
        existing = {c.name for c in self.client.get_collections().collections}
        if settings.dense_collection not in existing:
            return []

        dense_result = self.client.query_points(
            settings.dense_collection,
            query=query_vector,
            limit=k,
        )
        dense_hits = dense_result.points

        sparse_hits = []
        if settings.sparse_collection in existing:
            sv = _sparse_vector(query_text)
            if sv.indices:
                sparse_result = self.client.query_points(
                    settings.sparse_collection,
                    query=sv,
                    using="bm25",
                    limit=k,
                )
                sparse_hits = sparse_result.points

        scores: dict[str, float] = {}
        id_to_payload: dict[str, dict] = {}

        for rank, hit in enumerate(dense_hits):
            pt_id = str(hit.id)
            scores[pt_id] = scores.get(pt_id, 0.0) + 1.0 / (60 + rank + 1)
            id_to_payload[pt_id] = hit.payload

        for rank, hit in enumerate(sparse_hits):
            pt_id = str(hit.id)
            scores[pt_id] = scores.get(pt_id, 0.0) + 1.0 / (60 + rank + 1)
            id_to_payload.setdefault(pt_id, hit.payload)

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:k]

        return [
            Chunk(
                id=id_to_payload[pt_id]["_chunk_id"],
                text=id_to_payload[pt_id]["text"],
                vector=[],
                metadata={
                    k: v
                    for k, v in id_to_payload[pt_id].items()
                    if k not in ("_chunk_id", "text")
                },
            )
            for pt_id, _ in ranked
        ]

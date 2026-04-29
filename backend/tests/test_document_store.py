import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from document_store import Chunk, DocumentStore
from config import settings

_TEST_DENSE = settings.dense_collection + "_test"
_TEST_SPARSE = settings.sparse_collection + "_test"


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setattr(settings, "dense_collection", _TEST_DENSE)
    monkeypatch.setattr(settings, "sparse_collection", _TEST_SPARSE)
    ds = DocumentStore()
    for name in (_TEST_DENSE, _TEST_SPARSE):
        try:
            ds.client.delete_collection(name)
        except Exception:
            pass
    yield ds
    for name in (_TEST_DENSE, _TEST_SPARSE):
        try:
            ds.client.delete_collection(name)
        except Exception:
            pass


def _chunk(id: str, text: str, vector: list[float]) -> Chunk:
    return Chunk(id=id, text=text, vector=vector)


def test_upsert_and_hybrid_search_ranks_relevant_first(store):
    chunks = [
        _chunk("1", "cold electronics detector calibration cryogenic", [1.0, 0.0, 0.0]),
        _chunk("2", "quantum mechanics wave function particle", [0.0, 1.0, 0.0]),
        _chunk("3", "machine learning neural network training", [0.0, 0.0, 1.0]),
        _chunk("4", "photon detection efficiency optics lens", [0.5, 0.5, 0.0]),
        _chunk("5", "protein folding biology genetics enzyme", [0.0, 0.5, 0.5]),
    ]
    store.upsert(chunks)

    results = store.hybrid_search(
        query_vector=[1.0, 0.0, 0.0],
        query_text="cold electronics cryogenic detector",
        k=5,
    )

    assert len(results) >= 1
    assert results[0].id == "1"


def test_hybrid_search_empty_collection_returns_empty(store):
    results = store.hybrid_search(
        query_vector=[1.0, 0.0, 0.0],
        query_text="cold electronics",
        k=5,
    )
    assert results == []

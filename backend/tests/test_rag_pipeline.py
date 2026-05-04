import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from config import settings
from document_store import DocumentStore
from rag_pipeline import ingest, query

_TEST_DENSE = settings.dense_collection + "_rag_test"
_TEST_SPARSE = settings.sparse_collection + "_rag_test"


@pytest.fixture(autouse=True)
def isolate_collections(monkeypatch):
    monkeypatch.setattr(settings, "dense_collection", _TEST_DENSE)
    monkeypatch.setattr(settings, "sparse_collection", _TEST_SPARSE)
    store = DocumentStore()
    for name in (_TEST_DENSE, _TEST_SPARSE):
        try:
            store.client.delete_collection(name)
        except Exception:
            pass
    yield
    for name in (_TEST_DENSE, _TEST_SPARSE):
        try:
            store.client.delete_collection(name)
        except Exception:
            pass


def test_ingest_returns_doc_id_and_query_returns_matching_chunk(tmp_path):
    doc = tmp_path / "detector.txt"
    doc.write_text(
        "Cold electronics operate at cryogenic temperatures near the liquid argon detector. "
        "Signal amplification occurs at 87 Kelvin to minimize thermal noise."
    )

    doc_id = ingest(doc)
    assert isinstance(doc_id, str) and len(doc_id) > 0

    results = query("cryogenic cold electronics liquid argon detector", top_k=3)
    assert len(results) >= 1
    assert results[0].doc_id == doc_id


def test_no_cross_contamination_between_documents(tmp_path):
    doc1 = tmp_path / "physics.txt"
    doc1.write_text(
        "The liquid argon time projection chamber measures ionization from charged particles. "
        "Cold electronics amplify signals at cryogenic temperatures near the detector anode wires."
    )

    doc2 = tmp_path / "biology.txt"
    doc2.write_text(
        "Genome sequencing identifies nucleotide patterns across chromosomes. "
        "Protein synthesis involves ribosomal translation of messenger RNA transcripts."
    )

    ingest(doc1)
    ingest(doc2)

    results = query("liquid argon ionization cold electronics cryogenic", top_k=1)
    assert len(results) >= 1
    assert results[0].source == "physics.txt"

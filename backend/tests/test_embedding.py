import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from embedding import embed


def test_embed_returns_nonempty_float_list():
    result = embed("test")
    assert isinstance(result, list)
    assert len(result) > 0
    assert all(isinstance(v, float) for v in result)


def test_embed_identical_text_returns_identical_vectors():
    v1 = embed("hello world")
    v2 = embed("hello world")
    assert v1 == v2

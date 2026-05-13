"""Session-scoped RAG chat for the /monitor flow.

Wraps Ollama chat with three layers of grounding:
  1. A session-context block built from the current FEMB run state
     (FEMB serials, pass/fail counts, failed tests, persisted diagnostics).
  2. Qdrant RAG retrieval against ingested QC documentation.
  3. Recent chat history persisted in femb_session_chats.

The existing /chat path is untouched; this module is additive.
"""

from typing import AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

import monitor_db
from config import settings
from monitor_session import get_session
from rag_pipeline import query as rag_query
from sse import DONE, event

_llm = ChatOllama(
    model=settings.reasoning_model,
    base_url=settings.ollama_base_url,
    reasoning=settings.reasoning_model_think,
)

_BASE_SYSTEM = (
    "You are an expert cold electronics QC assistant. The operator is reviewing "
    "one specific FEMB QC session and asking questions about it. Use the "
    "SESSION CONTEXT below first; supplement with the RETRIEVED DOCUMENTATION "
    "when relevant. Be concise. Cite test IDs (e.g. `t3`) and FEMB serials when "
    "applicable. If the session context does not contain the answer, say so "
    "rather than guessing."
)

_HISTORY_TURNS = 6  # last N messages (3 turns) fed back into the model
_DIAGNOSTIC_EXCERPT_CHARS = 4000  # per-FEMB cap in the session-context block


def _build_session_context(meta, runs: list[dict]) -> str:
    runs_by_femb = {r["femb_id"]: r for r in runs}
    lines: list[str] = [
        f"Run dir: `{meta.rel_path}`",
        f"Started: {meta.started_at or 'unknown'}",
        f"Run type: `{meta.test_type_hint}`",
        f"FEMBs in session: {len(meta.fembs)}",
        "",
    ]
    for femb in meta.fembs:
        r = runs_by_femb.get(femb.femb_id)
        if r is None:
            lines.append(
                f"### FEMB {femb.femb_id} — `{femb.serial}`  (no persisted record yet; run in progress)"
            )
            continue
        status = "PASS" if r["passed"] else "FAIL"
        lines.append(
            f"### FEMB {femb.femb_id} — `{femb.serial}`  ({status}, "
            f"{r['n_failed']}/{r['n_tests']} tests failed)"
        )
        if r.get("summary_md"):
            lines.append(f"**Summary:** {r['summary_md']}")
        diag = (r.get("diagnostic_md") or "").strip()
        if diag and r["n_failed"]:
            excerpt = diag[:_DIAGNOSTIC_EXCERPT_CHARS]
            lines.append("**Failure diagnostics:**")
            lines.append(excerpt)
        lines.append("")
    return "\n".join(lines).strip()


def get_chat_history(session_id_b64: str) -> list[dict]:
    meta = get_session(session_id_b64)
    if meta is None:
        return []
    db_session_id = monitor_db.store.upsert_session(meta.rel_path, meta.started_at)
    return monitor_db.store.get_chat_history(db_session_id)


def clear_chat_history(session_id_b64: str) -> bool:
    meta = get_session(session_id_b64)
    if meta is None:
        return False
    db_session_id = monitor_db.store.upsert_session(meta.rel_path, meta.started_at)
    monitor_db.store.clear_chat_history(db_session_id)
    return True


async def stream_chat(session_id_b64: str, message: str) -> AsyncIterator[str]:
    meta = get_session(session_id_b64)
    if meta is None:
        yield event({"type": "error", "message": "session not found"})
        yield DONE
        return

    db_session_id = monitor_db.store.upsert_session(meta.rel_path, meta.started_at)
    runs = monitor_db.store.list_femb_runs(db_session_id)
    session_context = _build_session_context(meta, runs)

    chunks = rag_query(
        message,
        top_k=settings.retrieval_top_k,
        reranker_enabled=settings.reranker_enabled,
        generation_top_k=settings.generation_top_k,
    )

    sources = sorted({c.source for c in chunks if c.source})
    if sources:
        yield event({"type": "sources", "sources": sources})
    if chunks:
        yield event({
            "type": "retrieval",
            "chunks": [
                {
                    "source": c.source,
                    "chunk_index": c.chunk_index,
                    "rrf_score": round(c.rrf_score, 4),
                    "in_dense": c.in_dense,
                    "in_sparse": c.in_sparse,
                    "text": c.text,
                }
                for c in chunks
            ],
        })

    retrieved = "\n\n".join(c.text for c in chunks)

    history_rows = monitor_db.store.get_chat_history(db_session_id)[-_HISTORY_TURNS:]
    history_msgs: list[HumanMessage | AIMessage] = []
    for r in history_rows:
        if r["role"] == "user":
            history_msgs.append(HumanMessage(content=r["content"]))
        elif r["role"] == "assistant":
            history_msgs.append(AIMessage(content=r["content"]))

    monitor_db.store.add_chat_message(db_session_id, "user", message)

    system_text = (
        f"{_BASE_SYSTEM}\n\n"
        f"## Session Context\n{session_context}\n\n"
        + (f"## Retrieved Documentation\n{retrieved}\n" if retrieved else "")
    )

    messages: list = [SystemMessage(content=system_text), *history_msgs, HumanMessage(content=message)]

    collected: list[str] = []
    try:
        async for chunk in _llm.astream(messages):
            text = getattr(chunk, "content", "") or ""
            if text:
                collected.append(text)
                yield event({"type": "token", "text": text})
    except Exception as exc:
        yield event({"type": "error", "message": f"LLM stream failed: {exc}"})

    if collected:
        monitor_db.store.add_chat_message(db_session_id, "assistant", "".join(collected))

    yield DONE

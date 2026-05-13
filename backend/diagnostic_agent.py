from typing import Any, AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool as lc_tool
from langchain_ollama import ChatOllama

from config import settings
from femb_test_schema import GAIN_MAP, PEAKING_MAP, SNC_MAP, TEST_ITEMS, build_llm_reference
from rag_pipeline import query as rag_query

_SYSTEM_PROMPT = "\n\n".join(
    [
        (
            "You are the Diagnostic Agent in a DUNE cold electronics QA/QC workflow. "
            "You receive QC analysis findings for a FEMB (Front-End Motherboard). Your job is to:\n"
            "1. Explain what each fault means in plain language for the operator.\n"
            "2. Identify whether the root cause is at board, chip, or channel level.\n"
            "3. Recommend the most specific next action (hardware inspection, software command, or re-run).\n"
            "4. Prioritise chip-level and board-level faults — they affect many channels at once.\n"
            "Be concise. Do not pad with generic advice — every sentence should be actionable."
        ),
        build_llm_reference(),
        (
            "## LArASIC Parameter Encoding\n\n"
            "When recommending a DAQ command, use these exact register values:\n\n"
            "| Human label | Parameter | Register bits |\n"
            "|-------------|-----------|---------------|\n"
            "| 200 mV baseline | snc | snc=1 |\n"
            "| 900 mV baseline | snc | snc=0 |\n"
            "| 4.7 mV/fC gain | sg | sg0=1, sg1=1 |\n"
            "| 7.8 mV/fC gain | sg | sg0=1, sg1=0 |\n"
            "| 14 mV/fC gain  | sg | sg0=0, sg1=0 |\n"
            "| 25 mV/fC gain  | sg | sg0=0, sg1=1 |\n"
            "| 0.5 µs peaking | st | st0=0, st1=1 |\n"
            "| 1.0 µs peaking | st | st0=1, st1=0 |\n"
            "| 2.0 µs peaking | st | st0=1, st1=1 |\n"
            "| 3.0 µs peaking | st | st0=1, st1=1 |\n\n"
            "Note: peaking time encoding is counter-intuitive — lower peaking time does NOT mean lower register value."
        ),
    ]
)


@lc_tool
def take_data(
    slot: int,
    snc_label: str,
    gain_label: str,
    peaking_label: str,
    num_samples: int = 10,
) -> dict[str, Any]:
    """Validate LArASIC DAQ parameters and return resolved register bits.

    snc_label:     '200mV' or '900mV'
    gain_label:    '4.7mV/fC', '7.8mV/fC', '14mV/fC', or '25mV/fC'
    peaking_label: '0.5us', '1.0us', '2.0us', or '3.0us'
    """
    errors = []
    if snc_label not in SNC_MAP:
        errors.append(f"snc_label must be one of {list(SNC_MAP)}, got {snc_label!r}")
    if gain_label not in GAIN_MAP:
        errors.append(f"gain_label must be one of {list(GAIN_MAP)}, got {gain_label!r}")
    if peaking_label not in PEAKING_MAP:
        errors.append(
            f"peaking_label must be one of {list(PEAKING_MAP)}, got {peaking_label!r}"
        )
    if errors:
        return {"error": "; ".join(errors)}

    sg0, sg1 = GAIN_MAP[gain_label]
    st0, st1 = PEAKING_MAP[peaking_label]
    return {
        "slot": slot,
        "snc_label": snc_label,
        "gain_label": gain_label,
        "peaking_label": peaking_label,
        "num_samples": num_samples,
        "registers": {
            "snc": SNC_MAP[snc_label],
            "sg0": sg0,
            "sg1": sg1,
            "st0": st0,
            "st1": st1,
        },
    }


_llm = ChatOllama(
    model=settings.reasoning_model,
    base_url=settings.ollama_base_url,
    reasoning=settings.reasoning_model_think,
)

_llm_with_tools = _llm


# ── /monitor flow: per-failed-report diagnostic ────────────────────────────

_FAILED_REPORT_PROMPT = (
    "You are diagnosing a single failed FEMB QC test. Be concise and "
    "actionable. Structure your reply as three short sections:\n\n"
    "**What failed.** 2–3 sentences identifying the failed measurement and "
    "the metric that went out of spec.\n\n"
    "**Likely cause.** One paragraph. Pick the single most likely root cause "
    "based on the test type and any retrieved context.\n\n"
    "**Next action.** A specific operator action — a command, a register "
    "reset, a cable check. Avoid generic advice."
)


def _test_id_to_test_num(test_id: str) -> int | None:
    """t14 -> 14; tolerant of malformed input."""
    s = test_id.lstrip("t")
    return int(s) if s.isdigit() else None


def _retrieval_seed(test_id: str, test_type_hint: str) -> str:
    """Build a retrieval query from test schema if known, else fall back."""
    num = _test_id_to_test_num(test_id)
    spec = TEST_ITEMS.get(num) if num is not None else None
    hint = test_type_hint or "FEMB QC"
    if spec is None:
        return f"cold electronics FEMB QC failure: test {test_id} test_type={hint}"
    faults = ", ".join(spec["fault_types"].keys())
    return (
        f"cold electronics FEMB QC failure: {spec['name']} ({spec['description']}). "
        f"Possible fault types: {faults}. test_type={hint}"
    )


def _schema_snippet(test_id: str) -> str:
    """Return a compact test-spec reference for the prompt, or empty if unknown."""
    num = _test_id_to_test_num(test_id)
    spec = TEST_ITEMS.get(num) if num is not None else None
    if spec is None:
        return f"Test `{test_id}` is not in the canonical schema."
    lines = [
        f"Test `{test_id}` — **{spec['name']}** ({spec['granularity']}-level): {spec['description']}",
        "Possible faults:",
    ]
    for fault, fspec in spec["fault_types"].items():
        lines.append(f"- `{fault}`: {fspec['description']}. Action: {fspec['action']}.")
    return "\n".join(lines)


async def run_diagnostic_for_failed_report(
    md_text: str,
    test_id: str,
    femb_id: str,
    femb_serial: str = "",
    test_type_hint: str = "",
) -> AsyncIterator[dict]:
    """Yield SSE payload dicts for diagnosing a single failed report.

    Each yielded dict has at least `type`, `femb_id`, and `test_id`. Caller
    (monitor_session.watch_session) wraps each in the SSE wire format.
    """
    seed = _retrieval_seed(test_id, test_type_hint)
    chunks = rag_query(
        seed,
        top_k=settings.retrieval_top_k,
        reranker_enabled=settings.reranker_enabled,
        generation_top_k=settings.generation_top_k,
    )

    sources = sorted({c.source for c in chunks if c.source})
    if sources:
        yield {
            "type": "diagnostic_sources",
            "femb_id": femb_id,
            "test_id": test_id,
            "sources": sources,
        }
    if chunks:
        yield {
            "type": "diagnostic_retrieval",
            "femb_id": femb_id,
            "test_id": test_id,
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
        }

    context = "\n\n".join(c.text for c in chunks)
    schema_snippet = _schema_snippet(test_id)
    excerpt = md_text[:6000]

    user_msg = (
        f"FEMB **{femb_serial or femb_id}** (slot `{femb_id}`) failed test `{test_id}`"
        + (f" of run type `{test_type_hint}`" if test_type_hint else "")
        + ".\n\n"
        f"### Test specification\n{schema_snippet}\n\n"
        f"### Failed report (markdown excerpt)\n```markdown\n{excerpt}\n```\n\n"
        + (f"### Retrieved context\n{context}\n\n" if context else "")
        + "Diagnose this failure following the response format in your instructions."
    )

    messages = [
        SystemMessage(content=_FAILED_REPORT_PROMPT),
        HumanMessage(content=user_msg),
    ]

    async for chunk in _llm.astream(messages):
        text = getattr(chunk, "content", "") or ""
        if text:
            yield {
                "type": "diagnostic_token",
                "femb_id": femb_id,
                "test_id": test_id,
                "text": text,
            }

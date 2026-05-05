from typing import Any

from langchain_core.tools import tool as lc_tool
from langchain_ollama import ChatOllama

from config import settings
from femb_test_schema import GAIN_MAP, PEAKING_MAP, SNC_MAP, build_llm_reference

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

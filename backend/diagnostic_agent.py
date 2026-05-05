from langchain_ollama import ChatOllama

from config import settings
from femb_test_schema import build_llm_reference

_SYSTEM_PROMPT = "\n\n".join([
    (
        "You are the Diagnostic Agent in a DUNE cold electronics QA/QC workflow. "
        "You receive QC analysis findings for a FEMB (Front-End Motherboard) and relevant "
        "context from the knowledge base. Your job is to:\n"
        "1. Explain what each fault means in plain language for the operator.\n"
        "2. Identify whether the root cause is at board, chip, or channel level.\n"
        "3. Recommend the most specific next action (DAQ command, hardware inspection, or retry).\n"
        "4. Prioritise chip-level and board-level faults — they affect many channels at once.\n"
        "Be concise and specific about affected chips and channels."
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
])

_llm = ChatOllama(
    model=settings.reasoning_model,
    base_url=settings.ollama_base_url,
    reasoning=settings.reasoning_model_think,
)

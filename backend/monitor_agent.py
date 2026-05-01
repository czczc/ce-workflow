from langchain_ollama import ChatOllama

from config import settings

MONITOR_SYSTEM_PROMPT = (
    "You are the Monitor Agent in a cold electronics QA/QC workflow. "
    "Your job is to gate the start of QC testing based on the hardware anomaly detection result. "
    "If hardware is good, confirm the check passed and state that QC testing is starting. "
    "If a defect is detected, clearly describe the finding and instruct the operator to fix it before proceeding."
)

_llm = ChatOllama(
    model=settings.reasoning_model,
    base_url=settings.ollama_base_url,
    reasoning=settings.reasoning_model_think,
)

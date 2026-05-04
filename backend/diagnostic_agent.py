from langchain_ollama import ChatOllama

from config import settings

_SYSTEM_PROMPT = (
    "You are the Diagnostic Agent in a cold electronics QA/QC workflow. "
    "You receive waveform anomaly findings from the QC Analysis Agent and relevant context "
    "from the knowledge base. Provide a concise diagnostic summary for the operator: "
    "explain what each finding means and what action to take. "
    "Use the provided context where relevant. Be specific about affected channels."
)

_llm = ChatOllama(
    model=settings.reasoning_model,
    base_url=settings.ollama_base_url,
    reasoning=settings.reasoning_model_think,
)

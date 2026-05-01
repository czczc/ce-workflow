import json
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph

from config import settings
from rag_pipeline import query as rag_query

_SUGGESTED_ACTIONS = {
    "baseline_drift": "Inspect grounding and shielding; check power supply stability",
    "high_noise": "Check cable routing and shielding; verify ADC bias settings",
    "stuck_bit": "Replace ASIC or inspect for loose connections; likely hardware fault",
    "shape_anomaly": "Check for intermittent connections or cross-talk from adjacent channels",
}

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


class DiagnosticState(TypedDict):
    findings: dict
    rag_chunks: list   # serialised chunk dicts for SSE emission
    rag_context: str
    diagnosis: list    # [{channel, anomaly_type, suggested_action}]
    response: str


async def retrieve_context(state: DiagnosticState) -> dict:
    anomalies = state["findings"].get("anomalies", [])
    if not anomalies:
        return {"rag_chunks": [], "rag_context": ""}

    anomaly_types = list({issue for a in anomalies for issue in a["issues"]})
    query_text = f"cold electronics ADC waveform anomaly: {', '.join(anomaly_types)}"
    chunks = rag_query(query_text, top_k=settings.retrieval_top_k)

    serialised = [
        {
            "source": c.metadata.get("source", ""),
            "chunk_index": c.metadata.get("chunk_index", 0),
            "rrf_score": round(c.metadata.get("_rrf_score", 0.0), 4),
            "in_dense": c.metadata.get("_in_dense", False),
            "in_sparse": c.metadata.get("_in_sparse", False),
            "text": c.text,
        }
        for c in chunks
    ]
    context = "\n\n".join(c.text for c in chunks)
    return {"rag_chunks": serialised, "rag_context": context}


async def build_diagnosis(state: DiagnosticState) -> dict:
    anomalies = state["findings"].get("anomalies", [])
    diagnosis = [
        {
            "channel": a["channel"],
            "anomaly_type": issue,
            "suggested_action": _SUGGESTED_ACTIONS.get(issue, "Investigate further"),
        }
        for a in anomalies
        for issue in a["issues"]
    ]
    return {"diagnosis": diagnosis}


async def narrate(state: DiagnosticState) -> dict:
    content = f"QC findings:\n```json\n{json.dumps(state['findings'], indent=2)}\n```\n\n"
    content += f"Structured diagnosis:\n```json\n{json.dumps(state['diagnosis'], indent=2)}\n```\n\n"
    if state["rag_context"]:
        content += f"Technical context from knowledge base:\n{state['rag_context']}\n\n"
    content += "Summarise the findings and recommended actions for the operator."

    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=content)]
    ai_message = await _llm.ainvoke(messages)
    return {"response": ai_message.content}


_builder = StateGraph(DiagnosticState)
_builder.add_node("retrieve_context", retrieve_context)
_builder.add_node("build_diagnosis", build_diagnosis)
_builder.add_node("narrate", narrate)
_builder.add_edge(START, "retrieve_context")
_builder.add_edge("retrieve_context", "build_diagnosis")
_builder.add_edge("build_diagnosis", "narrate")
_builder.add_edge("narrate", END)
graph = _builder.compile()


async def run_diagnostic_agent(findings: dict):
    yield f"data: {json.dumps({'type': 'token', 'text': '\n\n*Diagnostic Agent: Analyzing findings...*\n\n'})}\n\n"

    async for mode, data in graph.astream(
        {"findings": findings, "rag_chunks": [], "rag_context": "", "diagnosis": [], "response": ""},
        stream_mode=["messages", "updates"],
    ):
        if mode == "updates":
            if "retrieve_context" in data:
                chunks = data["retrieve_context"].get("rag_chunks", [])
                if chunks:
                    sources = sorted({c["source"] for c in chunks if c.get("source")})
                    yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
                    yield f"data: {json.dumps({'type': 'retrieval', 'chunks': chunks})}\n\n"
            elif "build_diagnosis" in data:
                diagnosis = data["build_diagnosis"].get("diagnosis", [])
                yield f"data: {json.dumps({'type': 'tool_result', 'tool': 'qc_diagnosis', 'result': diagnosis})}\n\n"
        elif mode == "messages":
            msg, _ = data
            if msg.content:
                yield f"data: {json.dumps({'type': 'token', 'text': msg.content})}\n\n"

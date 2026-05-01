import json
from typing import TypedDict

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph

from config import settings
from daq_agent import run_daq_agent

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


class MonitorState(TypedDict):
    hardware_result: dict
    response: str


async def check_hardware(state: MonitorState) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(settings.hardware_check_url)
            resp.raise_for_status()
            result = resp.json()
        except Exception as exc:
            result = {"status": "error", "detail": str(exc)}
    return {"hardware_result": result}


async def respond(state: MonitorState) -> dict:
    result = state["hardware_result"]
    messages = [
        SystemMessage(content=MONITOR_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Hardware anomaly detection result:\n```json\n{json.dumps(result, indent=2)}\n```\n\n"
                "Provide your assessment and next step."
            )
        ),
    ]
    ai_message = await _llm.ainvoke(messages)
    return {"response": ai_message.content}


_builder = StateGraph(MonitorState)
_builder.add_node("check_hardware", check_hardware)
_builder.add_node("respond", respond)
_builder.add_edge(START, "check_hardware")
_builder.add_edge("check_hardware", "respond")
_builder.add_edge("respond", END)
graph = _builder.compile()


async def run_monitor_agent():
    yield f"data: {json.dumps({'type': 'token', 'text': '*Checking hardware status...*\n\n'})}\n\n"

    hardware_status = None

    async for mode, data in graph.astream(  # type: ignore[misc]
        {"hardware_result": {}, "response": ""},
        stream_mode=["messages", "updates"],
    ):
        if mode == "updates" and "check_hardware" in data:  # type: ignore[operator]
            result = data["check_hardware"].get("hardware_result", {})  # type: ignore[index]
            hardware_status = result.get("status")
            yield f"data: {json.dumps({'type': 'tool_result', 'tool': 'hardware_anomaly_check', 'result': result})}\n\n"
        elif mode == "messages":
            msg, _ = data  # type: ignore[misc]
            if msg.content:  # type: ignore[union-attr]
                yield f"data: {json.dumps({'type': 'token', 'text': msg.content})}\n\n"  # type: ignore[union-attr]

    if hardware_status == "good":
        async for event in run_daq_agent():
            yield event

    yield "data: [DONE]\n\n"

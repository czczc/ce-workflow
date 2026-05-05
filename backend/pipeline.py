import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

import httpx
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph

from anomaly_taxonomy import SUGGESTED_ACTIONS as _SUGGESTED_ACTIONS
from catalog_agent import _build_summary, fetch_chip_serials, fetch_component_history
from run_store import store as _run_store
from config import settings
from daq_agent import N_CHANNELS, generate_ce_agent_data, save_ce_agent_run
from diagnostic_agent import _SYSTEM_PROMPT as _DIAG_PROMPT, _llm_with_tools, take_data
from monitor_agent import MONITOR_SYSTEM_PROMPT
from rag_pipeline import query as rag_query
from sse import DONE, event

_llm = ChatOllama(
    model=settings.reasoning_model,
    base_url=settings.ollama_base_url,
    reasoning=settings.reasoning_model_think,
)


class _StartupInputs(TypedDict):
    inject_anomalies: bool
    component_id: str

class _HardwareIO(TypedDict):
    hardware_result: dict
    hardware_status: str

class _DAQIO(TypedDict):
    run_dir: str
    daq_summary: dict

class _QCIO(TypedDict):
    findings: dict

class _RAGIO(TypedDict):
    rag_chunks: list
    rag_context: str

class _DiagnosisIO(TypedDict):
    diagnosis: list

class _NarrateIO(TypedDict, total=False):
    take_data_calls: list

class _CatalogIO(TypedDict):
    run_id: int
    passed: bool
    summary: str
    mcp_warning: str

class PipelineState(
    _StartupInputs, _HardwareIO, _DAQIO, _QCIO, _RAGIO, _DiagnosisIO, _NarrateIO, _CatalogIO,
    total=False,
):
    pass

class _NarrateIn(_QCIO, _RAGIO, _DiagnosisIO):
    pass

class _CatalogIn(_QCIO, _StartupInputs):
    pass


# ── nodes ────────────────────────────────────────────────────────────────────

async def check_hardware(state: PipelineState) -> _HardwareIO:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(settings.hardware_check_url)
            resp.raise_for_status()
            result = resp.json()
        except Exception as exc:
            result = {"status": "error", "detail": str(exc)}
    return {"hardware_result": result, "hardware_status": result.get("status", "error")}


async def monitor_respond(state: _HardwareIO) -> dict:
    messages = [
        SystemMessage(content=MONITOR_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Hardware anomaly detection result:\n```json\n"
                f"{json.dumps(state['hardware_result'], indent=2)}\n```\n\n"
                "Provide your assessment and next step."
            )
        ),
    ]
    await _llm.ainvoke(messages)
    return {}


async def daq_acquire(state: _StartupInputs) -> _DAQIO:
    data = generate_ce_agent_data(inject_faults=state["inject_anomalies"])
    run_dir = save_ce_agent_run(data)
    summary = {
        "n_channels": N_CHANNELS,
        "femb_serial": data["femb_serial"],
        "slot": data["slot"],
        "config_label": data["config_label"],
        "slot_passed": data["slot_passed"],
        "run_dir": str(run_dir),
    }
    return {"run_dir": str(run_dir), "daq_summary": summary}


async def qc_analyze(state: _DAQIO) -> _QCIO:
    from qc_analysis_agent import flag_anomalous_channels

    run_dir = Path(state["run_dir"])
    analysis = json.loads((run_dir / "channel_analysis.json").read_text())
    anomalies = flag_anomalous_channels(analysis["channels"])

    fault_files = sorted(p.name for p in run_dir.glob("*_F_*.md"))
    pass_files = sorted(p.name for p in run_dir.glob("*_P_*.md"))

    findings = {
        "run_dir": state["run_dir"],
        "femb_serial": analysis["femb_serial"],
        "slot": analysis["slot"],
        "config_label": analysis["config_label"],
        "n_channels": analysis["n_channels"],
        "n_anomalous": len(anomalies),
        "anomalies": anomalies,
        "fault_test_items": analysis["fault_test_items"],
        "pass_test_items": analysis["pass_test_items"],
        "slot_passed": analysis["slot_passed"],
        "board_faults": analysis.get("board_faults", []),
        "chip_faults": analysis.get("chip_faults", {}),
        "fault_files": fault_files,
        "pass_files": pass_files,
    }
    return {"findings": findings}


async def retrieve_context(state: _QCIO) -> _RAGIO:
    anomalies = state["findings"].get("anomalies", [])
    anomaly_types = list({issue for a in anomalies for issue in a["issues"]})
    query_text = f"cold electronics ADC waveform anomaly: {', '.join(anomaly_types)}"
    chunks = rag_query(query_text, top_k=settings.retrieval_top_k)
    serialised = [
        {
            "source": c.source,
            "chunk_index": c.chunk_index,
            "rrf_score": round(c.rrf_score, 4),
            "in_dense": c.in_dense,
            "in_sparse": c.in_sparse,
            "text": c.text,
        }
        for c in chunks
    ]
    return {"rag_chunks": serialised, "rag_context": "\n\n".join(c.text for c in chunks)}


async def build_diagnosis(state: _QCIO) -> _DiagnosisIO:
    diagnosis = [
        {
            "channel": a["channel"],
            "anomaly_type": issue,
            "suggested_action": _SUGGESTED_ACTIONS.get(issue, "Investigate further"),
        }
        for a in state["findings"].get("anomalies", [])
        for issue in a["issues"]
    ]
    return {"diagnosis": diagnosis}


async def narrate(state: _NarrateIn) -> _NarrateIO:
    content = f"QC findings:\n```json\n{json.dumps(state['findings'], indent=2)}\n```\n\n"
    content += f"Structured diagnosis:\n```json\n{json.dumps(state['diagnosis'], indent=2)}\n```\n\n"
    content += "Summarise the findings and recommended actions for the operator."
    messages = [SystemMessage(content=_DIAG_PROMPT), HumanMessage(content=content)]

    response = await _llm_with_tools.ainvoke(messages)
    take_data_calls: list = []
    if response.tool_calls:
        messages.append(response)
        for tc in response.tool_calls:
            result = take_data.invoke(tc["args"])
            take_data_calls.append({"name": tc["name"], "args": tc["args"], "result": result})
            messages.append(ToolMessage(content=json.dumps(result), tool_call_id=tc["id"]))
        await _llm.ainvoke(messages)

    return {"take_data_calls": take_data_calls}


async def catalog_write(state: _CatalogIn) -> _CatalogIO:
    findings = state["findings"]
    femb_serial = findings.get("femb_serial", "")
    component_history = None
    chip_serials = None
    mcp_warning = ""
    if femb_serial:
        component_history = await fetch_component_history(femb_serial, settings.django_mcp_url)
        chip_serials = await fetch_chip_serials(femb_serial, settings.django_mcp_url)
        if component_history is None:
            mcp_warning = f"Django DB MCP server unreachable ({settings.django_mcp_url}); report written without component history."
    summary = _build_summary(findings, component_history, chip_serials)
    run_id = _run_store.write_run(
        run_dir=findings["run_dir"],
        timestamp=datetime.now(timezone.utc).isoformat(),
        femb_serial=findings.get("femb_serial", ""),
        slot=findings.get("slot", 0),
        config_label=findings.get("config_label", ""),
        passed=1 if findings.get("slot_passed", not findings["n_anomalous"]) else 0,
        n_channels=findings["n_channels"],
        n_anomalous=findings["n_anomalous"],
        fault_test_items=findings.get("fault_test_items", []),
        board_faults=findings.get("board_faults", []),
        chip_faults=findings.get("chip_faults", {}),
        summary=summary,
    )
    return {"run_id": run_id, "passed": findings["n_anomalous"] == 0, "summary": summary, "mcp_warning": mcp_warning}


# ── routing ───────────────────────────────────────────────────────────────────

def _route_after_monitor(state: _HardwareIO) -> str:
    return "daq_acquire" if state["hardware_status"] == "good" else END


def _route_after_qc(state: _QCIO) -> str:
    return "retrieve_context" if state["findings"].get("n_anomalous", 0) > 0 else "catalog_write"


# ── graph ─────────────────────────────────────────────────────────────────────

_builder = StateGraph(PipelineState)
for _name, _fn in [
    ("check_hardware", check_hardware),
    ("monitor_respond", monitor_respond),
    ("daq_acquire", daq_acquire),
    ("qc_analyze", qc_analyze),
    ("retrieve_context", retrieve_context),
    ("build_diagnosis", build_diagnosis),
    ("narrate", narrate),
    ("catalog_write", catalog_write),
]:
    _builder.add_node(_name, _fn)

_builder.add_edge(START, "check_hardware")
_builder.add_edge("check_hardware", "monitor_respond")
_builder.add_conditional_edges("monitor_respond", _route_after_monitor)
_builder.add_edge("daq_acquire", "qc_analyze")
_builder.add_conditional_edges("qc_analyze", _route_after_qc)
_builder.add_edge("retrieve_context", "build_diagnosis")
_builder.add_edge("build_diagnosis", "narrate")
_builder.add_edge("narrate", "catalog_write")
_builder.add_edge("catalog_write", END)
graph = _builder.compile()

_INITIAL_STATE: _StartupInputs = {
    "inject_anomalies": True,
    "component_id": "",
}


async def run_pipeline(test: bool = False, component_id: str = ""):
    yield event({"type": "node_active", "node": "check_hardware"})
    yield event({"type": "token", "text": "*Monitor Agent: Checking hardware status...*\n\n"})

    hardware_status = None
    initial_state: PipelineState = {**_INITIAL_STATE, "inject_anomalies": test, "component_id": component_id}  # type: ignore[typeddict-item]

    async for mode, data in graph.astream(  # type: ignore[misc]
        initial_state,
        stream_mode=["messages", "updates"],
    ):
        if mode == "updates":  # type: ignore[operator]
            node, update = next(iter(data.items()))  # type: ignore[union-attr]
            update = update or {}  # type: ignore[assignment]

            if node == "check_hardware":
                result = update.get("hardware_result", {})
                hardware_status = result.get("status")
                yield event({"type": "tool_result", "tool": "hardware_anomaly_check", "result": result})

            elif node == "monitor_respond":
                yield event({"type": "node_active", "node": "monitor_respond"})
                if hardware_status == "good":
                    yield event({"type": "node_active", "node": "daq_acquire"})
                    yield event({"type": "token", "text": "\n\n*DAQ Agent: Acquiring waveform data...*\n\n"})

            elif node == "daq_acquire":
                summary = update.get("daq_summary", {})  # type: ignore[union-attr]
                run_name = Path(update.get("run_dir", "")).name  # type: ignore[union-attr]
                yield event({"type": "tool_result", "tool": "daq_acquire", "result": summary})
                serial = summary.get("femb_serial", "unknown")
                cfg = summary.get("config_label", "")
                yield event({"type": "token", "text": f"Acquired {N_CHANNELS}-channel data for FEMB `{serial}` (config: {cfg}). Saved to `{run_name}`.\n"})
                yield event({"type": "node_active", "node": "qc_analyze"})
                yield event({"type": "token", "text": "\n\n*QC Analysis Agent: Analyzing waveforms...*\n\n"})

            elif node == "qc_analyze":
                findings = update.get("findings", {})  # type: ignore[union-attr]
                yield event({"type": "tool_result", "tool": "qc_analysis", "result": findings})
                n_anom = findings.get("n_anomalous", 0)
                n_ch = findings.get("n_channels", 0)
                if n_anom:
                    lines = [f"**QC Analysis complete.** {n_anom}/{n_ch} channels flagged:\n"]
                    for a in findings.get("anomalies", []):
                        lines.append(f"- Channel {a['channel']:02d}: {', '.join(a['issues'])}")
                    yield event({"type": "token", "text": "\n".join(lines) + "\n"})
                    yield event({"type": "node_active", "node": "retrieve_context"})
                    yield event({"type": "token", "text": "\n\n*Diagnostic Agent: Analyzing findings...*\n\n"})
                else:
                    yield event({"type": "token", "text": f"**QC Analysis complete.** All {n_ch} channels passed. No anomalies detected.\n"})
                    yield event({"type": "node_active", "node": "catalog_write"})

            elif node == "retrieve_context":
                chunks = update.get("rag_chunks", [])  # type: ignore[union-attr]
                if chunks:
                    sources = sorted({c["source"] for c in chunks if c.get("source")})
                    yield event({"type": "sources", "sources": sources})
                    yield event({"type": "retrieval", "chunks": chunks})
                yield event({"type": "node_active", "node": "build_diagnosis"})

            elif node == "build_diagnosis":
                yield event({"type": "tool_result", "tool": "qc_diagnosis", "result": update.get("diagnosis", [])})  # type: ignore[union-attr]
                yield event({"type": "node_active", "node": "narrate"})

            elif node == "narrate":
                for call in update.get("take_data_calls", []):  # type: ignore[union-attr]
                    yield event({"type": "tool_result", "tool": "take_data", "result": call["result"]})

            elif node == "catalog_write":
                yield event({"type": "node_active", "node": "catalog_write"})
                yield event({"type": "token", "text": "\n\n*Catalog & Report Agent: Writing QC report...*\n\n"})
                if update.get("mcp_warning"):  # type: ignore[union-attr]
                    yield event({"type": "token", "text": f"> ⚠ {update['mcp_warning']}\n\n"})  # type: ignore[index]
                yield event({"type": "tool_result", "tool": "catalog_write", "result": {"run_id": update.get("run_id"), "passed": update.get("passed")}})  # type: ignore[union-attr]
                yield event({"type": "token", "text": str(update.get("summary", "")) + "\n"})  # type: ignore[union-attr]

        elif mode == "messages":
            msg, _ = data  # type: ignore[misc]
            if msg.content:  # type: ignore[union-attr]
                yield event({"type": "token", "text": msg.content})  # type: ignore[union-attr]

    yield event({"type": "node_done"})
    yield DONE

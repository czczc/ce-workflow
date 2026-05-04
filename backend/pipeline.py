import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

import h5py
import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph

from anomaly_taxonomy import SUGGESTED_ACTIONS as _SUGGESTED_ACTIONS
from catalog_agent import _build_summary, _connect, fetch_component_history
from config import settings
from daq_agent import N_CHANNELS, generate_waveform_data, save_waveforms
from diagnostic_agent import _SYSTEM_PROMPT as _DIAG_PROMPT
from monitor_agent import MONITOR_SYSTEM_PROMPT
from rag_pipeline import query as rag_query
from sse import DONE, event

_llm = ChatOllama(
    model=settings.reasoning_model,
    base_url=settings.ollama_base_url,
    reasoning=settings.reasoning_model_think,
)


class PipelineState(TypedDict):
    # monitor
    hardware_result: dict
    hardware_status: str
    # daq
    run_dir: str
    daq_summary: dict
    # qc analysis
    findings: dict
    # diagnostic
    rag_chunks: list
    rag_context: str
    diagnosis: list
    # catalog
    run_id: int
    passed: bool
    summary: str
    inject_anomalies: bool
    component_id: str
    mcp_warning: str


# ── nodes ────────────────────────────────────────────────────────────────────

async def check_hardware(state: PipelineState) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(settings.hardware_check_url)
            resp.raise_for_status()
            result = resp.json()
        except Exception as exc:
            result = {"status": "error", "detail": str(exc)}
    return {"hardware_result": result, "hardware_status": result.get("status", "error")}


async def monitor_respond(state: PipelineState) -> dict:
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


async def daq_acquire(state: PipelineState) -> dict:
    waveform = generate_waveform_data(inject_anomalies=state["inject_anomalies"])
    run_dir = save_waveforms(waveform)
    summary = {
        "n_channels": waveform["n_channels"],
        "n_samples": waveform["n_samples"],
        "channel_baselines": [ch["baseline"] for ch in waveform["channels"]],
        "run_dir": str(run_dir),
    }
    return {"run_dir": str(run_dir), "daq_summary": summary}


async def qc_analyze(state: PipelineState) -> dict:
    from qc_analysis_agent import _check_baseline, _check_noise_rms, _check_signal_shape

    run_dir = Path(state["run_dir"])
    channel_results, anomalies = [], []

    with h5py.File(run_dir / "waveforms.h5", "r") as f:
        for key in sorted(f.keys()):
            ch_idx = int(key.split("_")[1])
            samples = list(f[key][:])
            baseline = sum(samples) / len(samples)

            bl = _check_baseline(baseline)
            nr = _check_noise_rms(samples, baseline)
            ss = _check_signal_shape(samples, baseline)

            issues = []
            if not bl["ok"]:
                issues.append("baseline_drift")
            if not nr["ok"]:
                issues.append("high_noise")
            if ss["stuck"]:
                issues.append("stuck_bit")
            elif not ss["ok"]:
                issues.append("shape_anomaly")

            result = {
                "channel": ch_idx,
                "baseline": bl["baseline"],
                "noise_rms": nr["rms"],
                "outlier_fraction": ss["outlier_fraction"],
                "issues": issues,
            }
            channel_results.append(result)
            if issues:
                anomalies.append(result)

    findings = {
        "run_dir": state["run_dir"],
        "n_channels": len(channel_results),
        "n_anomalous": len(anomalies),
        "anomalies": anomalies,
    }
    return {"findings": findings}


async def retrieve_context(state: PipelineState) -> dict:
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


async def build_diagnosis(state: PipelineState) -> dict:
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


async def narrate(state: PipelineState) -> dict:
    content = f"QC findings:\n```json\n{json.dumps(state['findings'], indent=2)}\n```\n\n"
    content += f"Structured diagnosis:\n```json\n{json.dumps(state['diagnosis'], indent=2)}\n```\n\n"
    if state["rag_context"]:
        content += f"Technical context from knowledge base:\n{state['rag_context']}\n\n"
    content += "Summarise the findings and recommended actions for the operator."
    messages = [SystemMessage(content=_DIAG_PROMPT), HumanMessage(content=content)]
    await _llm.ainvoke(messages)
    return {}


async def catalog_write(state: PipelineState) -> dict:
    findings = state["findings"]
    component_history = None
    mcp_warning = ""
    if state.get("component_id"):
        component_history = await fetch_component_history(state["component_id"], settings.django_mcp_url)
        if component_history is None:
            mcp_warning = f"Django DB MCP server unreachable ({settings.django_mcp_url}); report written without component history."
    summary = _build_summary(findings, component_history)
    conn = _connect()
    cur = conn.execute(
        "INSERT INTO qc_runs (run_dir, timestamp, passed, n_channels, n_anomalous) VALUES (?, ?, ?, ?, ?)",
        (
            findings["run_dir"],
            datetime.now(timezone.utc).isoformat(),
            0 if findings["n_anomalous"] else 1,
            findings["n_channels"],
            findings["n_anomalous"],
        ),
    )
    run_id = cur.lastrowid
    conn.execute("INSERT INTO reports (run_id, summary) VALUES (?, ?)", (run_id, summary))
    conn.commit()
    conn.close()
    return {"run_id": run_id, "passed": findings["n_anomalous"] == 0, "summary": summary, "mcp_warning": mcp_warning}


# ── routing ───────────────────────────────────────────────────────────────────

def _route_after_monitor(state: PipelineState) -> str:
    return "daq_acquire" if state["hardware_status"] == "good" else END


def _route_after_qc(state: PipelineState) -> str:
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

_INITIAL_STATE: PipelineState = {
    "hardware_result": {}, "hardware_status": "",
    "run_dir": "", "daq_summary": {},
    "findings": {},
    "inject_anomalies": True,
    "rag_chunks": [], "rag_context": "", "diagnosis": [],
    "run_id": 0, "passed": False, "summary": "", "mcp_warning": "",
    "component_id": "",
}


async def run_pipeline(test: bool = False, component_id: str = ""):
    yield event({"type": "node_active", "node": "check_hardware"})
    yield event({"type": "token", "text": "*Monitor Agent: Checking hardware status...*\n\n"})

    hardware_status = None
    initial_state = {**_INITIAL_STATE, "inject_anomalies": test, "component_id": component_id}

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
                yield event({"type": "token", "text": f"Acquired {N_CHANNELS}-channel ADC waveform ({summary.get('n_samples')} samples/channel). Saved to `{run_name}`.\n"})
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

import json

from anomaly_taxonomy import SUGGESTED_ACTIONS
from femb_test_schema import TEST_ITEMS
from run_store import store


def _build_summary(findings: dict, component_history: dict | None = None) -> str:
    serial = findings.get("femb_serial", "unknown")
    slot = findings.get("slot", "?")
    config = findings.get("config_label", "")
    passed = findings.get("slot_passed", findings["n_anomalous"] == 0)

    status = "**QC PASS**" if passed else "**QC FAIL**"
    lines = [f"{status} — FEMB `{serial}` slot {slot} ({config})"]
    lines.append(f"Channels: {findings['n_channels']} total, {findings['n_anomalous']} anomalous")

    board_faults = findings.get("board_faults", [])
    if board_faults:
        lines.append("\n**Board-level faults:**")
        for fault in board_faults:
            action = SUGGESTED_ACTIONS.get(fault, "Investigate further")
            lines.append(f"  - `{fault}`: {action}")

    chip_faults = findings.get("chip_faults", {})
    if chip_faults:
        lines.append("\n**Chip-level faults:**")
        for chip_idx, fault in chip_faults.items():
            ch_range = f"ch {int(chip_idx)*16}–{int(chip_idx)*16+15}"
            action = SUGGESTED_ACTIONS.get(fault, "Investigate further")
            lines.append(f"  - Chip {chip_idx} ({ch_range}) `{fault}`: {action}")

    chip_fault_set = set(chip_faults.values())
    anomalies = findings.get("anomalies", [])
    channel_anomalies = [a for a in anomalies if not any(i in chip_fault_set for i in a["issues"])]
    if channel_anomalies:
        lines.append("\n**Channel-level faults:**")
        for a in channel_anomalies:
            for issue in a["issues"]:
                action = SUGGESTED_ACTIONS.get(issue, "Investigate further")
                lines.append(f"  - Ch {a['channel']:03d} (chip {a['chip']}) `{issue}`: {action}")

    fault_items = findings.get("fault_test_items", [])
    if fault_items:
        item_names = [f"t{t} ({TEST_ITEMS[t]['name']})" for t in fault_items if t in TEST_ITEMS]
        lines.append(f"\n**Failing test items:** {', '.join(item_names)}")

    if component_history and "error" not in component_history:
        sn = component_history.get("serial_number", "?")
        version = component_history.get("version", "?")
        status_str = component_history.get("status", "?")
        tests = component_history.get("tests", [])
        n_pass = sum(1 for t in tests if t.get("status") == "pass")
        lines.append(
            f"\n**Component Provenance (FEMB {sn}):**"
            f" version={version}, status={status_str},"
            f" tests={len(tests)} ({n_pass} pass)"
        )
        if tests:
            latest = tests[0]
            lines.append(
                f"  Latest: {latest['timestamp'][:10]}"
                f" {latest['test_env']} {latest['test_type']} @ {latest['site']}"
                f" → **{latest['status']}**"
            )

    return "\n".join(lines)


async def call_mcp_tool(name: str, arguments: dict, mcp_url: str):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            if result.content and result.content[0].type == "text":
                return json.loads(result.content[0].text)
    return None


async def fetch_component_history(serial_number: str, mcp_url: str) -> dict | None:
    try:
        return await call_mcp_tool("get_femb", {"serial_number": serial_number}, mcp_url)
    except Exception:
        return None


def list_reports(page: int = 1, limit: int = 20) -> dict:
    return store.list_reports(page=page, limit=limit)


def get_report(report_id: int) -> dict | None:
    return store.get_report(report_id)

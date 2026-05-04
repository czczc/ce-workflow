import json

from anomaly_taxonomy import SUGGESTED_ACTIONS
from run_store import store


def _build_summary(findings: dict, component_history: dict | None = None) -> str:
    if findings["n_anomalous"] == 0:
        lines = [f"**QC PASS** — All {findings['n_channels']} channels nominal."]
    else:
        lines = [f"**QC FAIL** — {findings['n_anomalous']}/{findings['n_channels']} channels anomalous:"]
        for a in findings["anomalies"]:
            for issue in a["issues"]:
                action = SUGGESTED_ACTIONS.get(issue, "Investigate further")
                lines.append(f"  - Ch {a['channel']:02d} `{issue}`: {action}")

    if component_history and "error" not in component_history:
        sn = component_history.get("serial_number", "?")
        version = component_history.get("version", "?")
        status = component_history.get("status", "?")
        tests = component_history.get("tests", [])
        n_pass = sum(1 for t in tests if t.get("status") == "pass")
        lines.append(
            f"\n**Component Provenance (FEMB {sn}):**"
            f" version={version}, status={status},"
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
    """Call any tool on the Django DB MCP server. Raises on connection or protocol failure."""
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
    """Query the Django DB MCP server for FEMB history. Returns None if unreachable."""
    try:
        return await call_mcp_tool("get_femb", {"serial_number": serial_number}, mcp_url)
    except Exception:
        return None


def list_reports(page: int = 1, limit: int = 20) -> dict:
    return store.list_reports(page=page, limit=limit)


def get_report(report_id: int) -> dict | None:
    return store.get_report(report_id)

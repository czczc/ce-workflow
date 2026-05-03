import json
import sqlite3
from pathlib import Path

from config import settings

_SUGGESTED_ACTIONS = {
    "baseline_drift": "Inspect grounding and shielding; check power supply stability",
    "high_noise": "Check cable routing and shielding; verify ADC bias settings",
    "stuck_bit": "Replace ASIC or inspect for loose connections; likely hardware fault",
    "shape_anomaly": "Check for intermittent connections or cross-talk from adjacent channels",
}

_DB_PATH = Path(__file__).parent / settings.sqlite_db_path


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS qc_runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_dir     TEXT    NOT NULL,
            timestamp   TEXT    NOT NULL,
            passed      INTEGER NOT NULL,
            n_channels  INTEGER NOT NULL,
            n_anomalous INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reports (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id  INTEGER NOT NULL REFERENCES qc_runs(id),
            summary TEXT    NOT NULL
        );
    """)
    conn.commit()
    return conn


def _build_summary(findings: dict, component_history: dict | None = None) -> str:
    if findings["n_anomalous"] == 0:
        lines = [f"**QC PASS** — All {findings['n_channels']} channels nominal."]
    else:
        lines = [f"**QC FAIL** — {findings['n_anomalous']}/{findings['n_channels']} channels anomalous:"]
        for a in findings["anomalies"]:
            for issue in a["issues"]:
                action = _SUGGESTED_ACTIONS.get(issue, "Investigate further")
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
    """Call any tool on the Django DB MCP server. Returns None if unreachable."""
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(mcp_url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)
                if result.content and result.content[0].type == "text":
                    return json.loads(result.content[0].text)
    except Exception:
        pass
    return None


async def fetch_component_history(serial_number: str, mcp_url: str) -> dict | None:
    """Query the Django DB MCP server for FEMB history. Returns None if unreachable."""
    return await call_mcp_tool("get_femb", {"serial_number": serial_number}, mcp_url)


_REPORT_QUERY = """
    SELECT r.id, r.run_dir, r.timestamp, r.passed, r.n_channels, r.n_anomalous, rp.summary
    FROM qc_runs r
    LEFT JOIN reports rp ON rp.run_id = r.id
"""


def list_reports(page: int = 1, limit: int = 20) -> dict:
    conn = _connect()
    total = conn.execute("SELECT COUNT(*) FROM qc_runs").fetchone()[0]
    rows = conn.execute(
        _REPORT_QUERY + "ORDER BY r.timestamp DESC LIMIT ? OFFSET ?",
        (limit, (page - 1) * limit),
    ).fetchall()
    conn.close()
    return {"items": [dict(row) for row in rows], "total": total}


def get_report(report_id: int) -> dict | None:
    conn = _connect()
    row = conn.execute(
        _REPORT_QUERY + "WHERE r.id = ?", (report_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

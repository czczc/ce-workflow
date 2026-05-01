import json
import sqlite3
from datetime import datetime, timezone
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


def _build_summary(findings: dict) -> str:
    if findings["n_anomalous"] == 0:
        return f"**QC PASS** — All {findings['n_channels']} channels nominal."
    lines = [f"**QC FAIL** — {findings['n_anomalous']}/{findings['n_channels']} channels anomalous:"]
    for a in findings["anomalies"]:
        for issue in a["issues"]:
            action = _SUGGESTED_ACTIONS.get(issue, "Investigate further")
            lines.append(f"  - Ch {a['channel']:02d} `{issue}`: {action}")
    return "\n".join(lines)


def list_reports() -> list[dict]:
    conn = _connect()
    rows = conn.execute("""
        SELECT r.id, r.run_dir, r.timestamp, r.passed, r.n_channels, r.n_anomalous, rp.summary
        FROM qc_runs r
        LEFT JOIN reports rp ON rp.run_id = r.id
        ORDER BY r.timestamp DESC
    """).fetchall()
    conn.close()
    return [dict(row) for row in rows]


async def run_catalog_agent(findings: dict):
    yield f"data: {json.dumps({'type': 'token', 'text': '\n\n*Catalog & Report Agent: Writing QC report...*\n\n'})}\n\n"

    summary = _build_summary(findings)

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

    yield f"data: {json.dumps({'type': 'tool_result', 'tool': 'catalog_write', 'result': {'run_id': run_id, 'passed': findings['n_anomalous'] == 0}})}\n\n"
    yield f"data: {json.dumps({'type': 'token', 'text': summary + chr(10)})}\n\n"

"""Read-only MCP server exposing the Django QC database (cets.sqlite3).

Run:  python mcp_django_db.py [--host 127.0.0.1] [--port 8001]
"""

import argparse
import sqlite3
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("cets-db")

_DB = Path(__file__).parent / "data" / "cets.sqlite3"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@mcp.tool()
def get_femb(serial_number: str) -> dict[str, Any]:
    """Return FEMB metadata and full test history for the given serial number."""
    conn = _conn()
    row = conn.execute(
        "SELECT id, serial_number, version, status, last_update FROM core_femb WHERE serial_number = ?",
        (serial_number,),
    ).fetchone()
    if row is None:
        return {"error": f"FEMB {serial_number!r} not found"}
    femb = dict(row)
    tests = conn.execute(
        "SELECT timestamp, test_type, test_env, site, status"
        " FROM core_femb_test WHERE femb_id = ? ORDER BY timestamp DESC",
        (femb["id"],),
    ).fetchall()
    conn.close()
    return {
        "serial_number": femb["serial_number"],
        "version": femb["version"],
        "status": femb["status"],
        "last_update": femb["last_update"],
        "tests": [dict(t) for t in tests],
    }


@mcp.tool()
def list_fembs(limit: int = 20) -> list[dict[str, Any]]:
    """List FEMBs ordered by most recently updated."""
    conn = _conn()
    rows = conn.execute(
        "SELECT serial_number, version, status, last_update FROM core_femb ORDER BY last_update DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CETS Django DB MCP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.run(transport="streamable-http")

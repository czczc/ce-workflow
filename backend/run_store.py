import sqlite3
from pathlib import Path

from config import settings

_SCHEMA = """
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
"""

_REPORT_QUERY = """
    SELECT r.id, r.run_dir, r.timestamp, r.passed, r.n_channels, r.n_anomalous, rp.summary
    FROM qc_runs r
    LEFT JOIN reports rp ON rp.run_id = r.id
"""


class RunStore:
    def __init__(self, db_path: Path | str):
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._open()
        conn.executescript(_SCHEMA)
        conn.commit()
        conn.close()

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def list_reports(self, page: int = 1, limit: int = 20) -> dict:
        conn = self._open()
        total = conn.execute("SELECT COUNT(*) FROM qc_runs").fetchone()[0]
        rows = conn.execute(
            _REPORT_QUERY + "ORDER BY r.timestamp DESC LIMIT ? OFFSET ?",
            (limit, (page - 1) * limit),
        ).fetchall()
        conn.close()
        return {"items": [dict(row) for row in rows], "total": total}

    def get_report(self, report_id: int) -> dict | None:
        conn = self._open()
        row = conn.execute(_REPORT_QUERY + "WHERE r.id = ?", (report_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def write_run(
        self,
        run_dir: str,
        timestamp: str,
        passed: int,
        n_channels: int,
        n_anomalous: int,
        summary: str,
    ) -> int:
        conn = self._open()
        cur = conn.execute(
            "INSERT INTO qc_runs (run_dir, timestamp, passed, n_channels, n_anomalous) VALUES (?, ?, ?, ?, ?)",
            (run_dir, timestamp, passed, n_channels, n_anomalous),
        )
        run_id = cur.lastrowid
        conn.execute("INSERT INTO reports (run_id, summary) VALUES (?, ?)", (run_id, summary))
        conn.commit()
        conn.close()
        return run_id


store = RunStore(Path(__file__).parent / settings.sqlite_db_path)

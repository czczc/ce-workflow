"""SQLite persistence for the /monitor flow.

Stores one row per QC session (run dir) and one row per FEMB within it.
Lives alongside the existing qc_runs / reports tables in qc.db — those
remain owned by the demo pipeline and are not touched here.
"""

import sqlite3
from pathlib import Path

from config import settings

_SCHEMA = """
    CREATE TABLE IF NOT EXISTS femb_sessions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        run_dir         TEXT    NOT NULL UNIQUE,
        started_at      TEXT,
        finished_at     TEXT,
        overall_passed  INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS femb_runs (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id    INTEGER NOT NULL REFERENCES femb_sessions(id),
        femb_id       TEXT    NOT NULL,
        femb_serial   TEXT    NOT NULL,
        n_tests       INTEGER NOT NULL DEFAULT 0,
        n_failed      INTEGER NOT NULL DEFAULT 0,
        passed        INTEGER NOT NULL DEFAULT 0,
        summary_md    TEXT,
        diagnostic_md TEXT,
        UNIQUE (session_id, femb_id)
    );
"""


class MonitorStore:
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

    def upsert_session(self, run_dir: str, started_at: str | None) -> int:
        conn = self._open()
        cur = conn.execute(
            "INSERT INTO femb_sessions (run_dir, started_at) VALUES (?, ?) "
            "ON CONFLICT(run_dir) DO UPDATE SET started_at = COALESCE(femb_sessions.started_at, excluded.started_at) "
            "RETURNING id",
            (run_dir, started_at),
        )
        row = cur.fetchone()
        conn.commit()
        conn.close()
        return row["id"]

    def complete_session(self, session_id: int, finished_at: str, overall_passed: bool) -> None:
        conn = self._open()
        conn.execute(
            "UPDATE femb_sessions SET finished_at = ?, overall_passed = ? WHERE id = ?",
            (finished_at, 1 if overall_passed else 0, session_id),
        )
        conn.commit()
        conn.close()

    def get_session_by_rel_path(self, run_dir: str) -> dict | None:
        conn = self._open()
        row = conn.execute(
            "SELECT id, run_dir, started_at, finished_at, overall_passed "
            "FROM femb_sessions WHERE run_dir = ?",
            (run_dir,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_femb_run(self, session_id: int, femb_id: str) -> dict | None:
        conn = self._open()
        row = conn.execute(
            "SELECT * FROM femb_runs WHERE session_id = ? AND femb_id = ?",
            (session_id, femb_id),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_femb_run_by_id(self, run_id: int) -> dict | None:
        conn = self._open()
        row = conn.execute("SELECT * FROM femb_runs WHERE id = ?", (run_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def list_femb_runs(self, session_id: int) -> list[dict]:
        conn = self._open()
        rows = conn.execute(
            "SELECT * FROM femb_runs WHERE session_id = ? ORDER BY femb_id",
            (session_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def upsert_femb_run(
        self,
        session_id: int,
        femb_id: str,
        femb_serial: str,
        n_tests: int,
        n_failed: int,
        passed: bool,
        summary_md: str,
        diagnostic_md: str,
    ) -> int:
        conn = self._open()
        cur = conn.execute(
            "INSERT INTO femb_runs "
            "(session_id, femb_id, femb_serial, n_tests, n_failed, passed, summary_md, diagnostic_md) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(session_id, femb_id) DO UPDATE SET "
            "femb_serial = excluded.femb_serial, "
            "n_tests = excluded.n_tests, "
            "n_failed = excluded.n_failed, "
            "passed = excluded.passed, "
            "summary_md = excluded.summary_md, "
            "diagnostic_md = excluded.diagnostic_md "
            "RETURNING id",
            (session_id, femb_id, femb_serial, n_tests, n_failed,
             1 if passed else 0, summary_md, diagnostic_md),
        )
        row = cur.fetchone()
        conn.commit()
        conn.close()
        return row["id"]

    def update_diagnostic(self, femb_run_id: int, diagnostic_md: str | None) -> None:
        conn = self._open()
        conn.execute(
            "UPDATE femb_runs SET diagnostic_md = ? WHERE id = ?",
            (diagnostic_md, femb_run_id),
        )
        conn.commit()
        conn.close()


store = MonitorStore(Path(__file__).parent / settings.sqlite_db_path)

"""File-watching monitor for real QC runs.

Watches a single run directory under $QC_ROOT/Report/Time_*/ and streams
SSE events as the DAQ drops report_*.md and Final_Report_*.md files.

Pure async; no LangGraph. The diagnostic subgraph is wired in slice #60.
"""

import asyncio
import base64
import re
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

import monitor_db
import monitor_sync
import ssh_helper
from config import settings
from diagnostic_agent import run_diagnostic_for_failed_report, stream_femb_summary
from femb_test_schema import TEST_ITEMS
from sse import DONE, event

# Test number → short human-readable name (e.g. 1 → "pwr_consumption").
TEST_LABELS: dict[str, str] = {f"t{n}": spec["name"] for n, spec in TEST_ITEMS.items()}

# ─── Filename / dir-name patterns ──────────────────────────────────────────

REPORT_RE = re.compile(r"^report_FEMB_\d+_t(\d+)_([PF])_S(\d+)\.md$")
FINAL_RE = re.compile(r"^Final_Report_FEMB_(.+)\.md$")
TIME_DIR_RE = re.compile(r"^Time_(\d{4})_(\d{2})$")
RUN_DIR_PREFIX_RE = re.compile(r"^(\d{2})_(\d{2})_(\d{2})_(\d{2})_(.+)$")
FEMB_SUBDIR_RE = re.compile(r"^FEMB(.+?)_S(\d+)$")

DEBOUNCE_S = 0.1


# ─── Session metadata ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class FembInfo:
    femb_id: str           # "S0" / "S1"
    serial: str            # "BNL_FEMB_IO-1865-1L_00010"
    subdir: str            # FEMB subdir name within the run dir

    def to_json(self) -> dict:
        return {"femb_id": self.femb_id, "serial": self.serial, "subdir": self.subdir}


@dataclass(frozen=True)
class SessionMeta:
    session_id: str        # opaque, urlsafe base64 of the rel_path under $QC_ROOT/Report/
    rel_path: str          # "Time_2026_05/10_02_58_23_..."
    abs_path: Path
    dir_name: str
    started_at: str | None # ISO8601 or None if unparseable
    test_type_hint: str    # tail of dir name after the timestamp portion
    fembs: list[FembInfo]
    in_progress: bool      # True if any FEMB lacks a Final_Report

    def to_json(self) -> dict:
        return {
            "session_id": self.session_id,
            "rel_path": self.rel_path,
            "dir_name": self.dir_name,
            "started_at": self.started_at,
            "test_type_hint": self.test_type_hint,
            "fembs": [f.to_json() for f in self.fembs],
            "in_progress": self.in_progress,
        }


# ─── ID encoding ───────────────────────────────────────────────────────────

def _encode_session_id(rel_path: str) -> str:
    return base64.urlsafe_b64encode(rel_path.encode()).decode().rstrip("=")


def _decode_session_id(sid: str) -> str:
    pad = "=" * (-len(sid) % 4)
    return base64.urlsafe_b64decode(sid + pad).decode()


# ─── Parsers ───────────────────────────────────────────────────────────────

def _parse_time_parent(parent_name: str) -> tuple[int, int] | None:
    m = TIME_DIR_RE.match(parent_name)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _parse_run_dir_name(name: str, year: int, month: int) -> tuple[str | None, str]:
    """Return (iso_started_at, test_type_hint). Tolerant of unknown suffixes."""
    m = RUN_DIR_PREFIX_RE.match(name)
    if not m:
        return None, name
    dd, hh, mm, ss, tail = m.groups()
    try:
        dt = datetime(year, month, int(dd), int(hh), int(mm), int(ss))
        iso = dt.isoformat()
    except ValueError:
        iso = None
    # test_type_hint = last 1–2 underscore-separated tokens of the tail (e.g. "LN_QC")
    parts = tail.rsplit("_", 2)
    if len(parts) >= 2:
        hint = "_".join(parts[-2:]) if parts[-2].isupper() and parts[-2].isalpha() else parts[-1]
    else:
        hint = tail
    return iso, hint


def _discover_fembs(run_dir: Path) -> list[FembInfo]:
    fembs: list[FembInfo] = []
    if not run_dir.is_dir():
        return fembs
    for entry in sorted(run_dir.iterdir()):
        if not entry.is_dir():
            continue
        m = FEMB_SUBDIR_RE.match(entry.name)
        if not m:
            continue
        serial, slot = m.groups()
        fembs.append(FembInfo(femb_id=f"S{slot}", serial=serial, subdir=entry.name))
    return fembs


def _has_final_report(femb_dir: Path) -> bool:
    if not femb_dir.is_dir():
        return False
    return any(FINAL_RE.match(p.name) for p in femb_dir.iterdir())


def _build_session_meta(rel_path: str, abs_path: Path) -> SessionMeta | None:
    parent_name = Path(rel_path).parent.name
    parsed = _parse_time_parent(parent_name)
    started_at: str | None = None
    hint = abs_path.name
    if parsed is not None:
        year, month = parsed
        started_at, hint = _parse_run_dir_name(abs_path.name, year, month)

    fembs = _discover_fembs(abs_path)
    in_progress = any(not _has_final_report(abs_path / f.subdir) for f in fembs) or not fembs

    return SessionMeta(
        session_id=_encode_session_id(rel_path),
        rel_path=rel_path,
        abs_path=abs_path,
        dir_name=abs_path.name,
        started_at=started_at,
        test_type_hint=hint,
        fembs=fembs,
        in_progress=in_progress,
    )


# ─── Sessions listing ──────────────────────────────────────────────────────

def _run_to_dict(meta: SessionMeta) -> dict:
    """SessionMeta → API row with DB-derived status fields."""
    d = meta.to_json()
    db_row = monitor_db.store.get_session_by_rel_path(meta.rel_path)
    if db_row:
        d["persisted"] = True
        d["overall_passed"] = bool(db_row.get("overall_passed"))
        d["finished_at"] = db_row.get("finished_at")
    else:
        d["persisted"] = False
    # Compact status for the picker icon: in_progress | passed | failed | unopened
    if meta.in_progress:
        d["status"] = "in_progress"
    elif d["persisted"]:
        d["status"] = "passed" if d["overall_passed"] else "failed"
    else:
        d["status"] = "unopened"
    return d


def _scan_runs_in_month(time_dir: Path) -> list[dict]:
    """Return run dicts (newest first) for one Time_YYYY_MM directory."""
    metas: list[SessionMeta] = []
    for run_dir in time_dir.iterdir():
        if not run_dir.is_dir():
            continue
        rel = f"{time_dir.name}/{run_dir.name}"
        meta = _build_session_meta(rel, run_dir.resolve())
        if meta is not None:
            metas.append(meta)
    metas.sort(key=lambda m: m.started_at or "", reverse=True)
    return [_run_to_dict(m) for m in metas]


def _local_list_sessions(month: str | None, *, from_local_cache: bool) -> dict:
    """Local-disk implementation of the listing. Used both as the dev/no-remote
    path and as the fallback when a configured remote is unreachable.
    """
    qc_root = Path(settings.qc_root).resolve()
    report_root = qc_root / "Report"
    if not report_root.is_dir():
        out = {"months": []} if month is None else {"name": month, "runs": []}
        return out

    def _mark(rows: list[dict]) -> list[dict]:
        if from_local_cache:
            for r in rows:
                r["from_local_cache"] = True
        return rows

    if month is not None:
        if not TIME_DIR_RE.match(month):
            return {"name": month, "runs": []}
        time_dir = report_root / month
        if not time_dir.is_dir():
            return {"name": month, "runs": []}
        return {"name": month, "runs": _mark(_scan_runs_in_month(time_dir))}

    months: list[dict] = []
    for time_dir in sorted(report_root.iterdir(), key=lambda p: p.name, reverse=True):
        if not time_dir.is_dir() or not TIME_DIR_RE.match(time_dir.name):
            continue
        runs = _mark(_scan_runs_in_month(time_dir))
        if runs:
            months.append({"name": time_dir.name, "runs": runs})
    return {"months": months}


# Remote-listing shell. Walks Report/<MONTH_GLOB>/<run>/<FEMB*> and emits one
# line per FEMB dir: "<rel_femb_path>|<has_final 0|1>". Caller validates MONTH.
_REMOTE_LIST_SCRIPT = (
    "set -u; "
    "cd {root}/Report 2>/dev/null || exit 2; "
    "find {glob} -mindepth 2 -maxdepth 2 -type d -name 'FEMB*' 2>/dev/null "
    "| while read d; do "
    "  if ls \"$d\"/Final_Report_*.md >/dev/null 2>&1; then echo \"$d|1\"; else echo \"$d|0\"; fi; "
    "done"
)


def _build_remote_list_cmd(month: str | None) -> str:
    import shlex
    root = shlex.quote(settings.remote_qc_root.rstrip("/"))
    # Caller validates month; the regex allow-list keeps this safe to inline.
    glob = month if month else "Time_*"
    return _REMOTE_LIST_SCRIPT.format(root=root, glob=glob)


def _parse_remote_list(output: str) -> dict[str, dict[str, str]]:
    """Parse `<rel>/Time_X/run/FEMBserial_Sslot|<0|1>` lines into a nested map:
    {f"{time_dir}/{run_dir}": {femb_subdir: has_final}}
    """
    by_run: dict[str, dict[str, str]] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        rel_femb, has_final = line.rsplit("|", 1)
        parts = rel_femb.split("/")
        if len(parts) != 3:
            continue
        time_dir, run_dir, femb_subdir = parts
        if not TIME_DIR_RE.match(time_dir) or not FEMB_SUBDIR_RE.match(femb_subdir):
            continue
        rel = f"{time_dir}/{run_dir}"
        by_run.setdefault(rel, {})[femb_subdir] = has_final.strip()
    return by_run


def _meta_from_remote(rel_path: str, femb_map: dict[str, str]) -> SessionMeta:
    """Build a SessionMeta from a remote-listing entry. abs_path is the
    local mirror path (may not exist yet — rsync materializes it on select)."""
    time_dir, run_dir = rel_path.split("/", 1)
    parent_year_month = _parse_time_parent(time_dir)
    started_at: str | None = None
    hint = run_dir
    if parent_year_month is not None:
        year, month = parent_year_month
        started_at, hint = _parse_run_dir_name(run_dir, year, month)

    fembs: list[FembInfo] = []
    in_progress = False
    for subdir, has_final in sorted(femb_map.items()):
        m = FEMB_SUBDIR_RE.match(subdir)
        if not m:
            continue
        serial, slot = m.groups()
        fembs.append(FembInfo(femb_id=f"S{slot}", serial=serial, subdir=subdir))
        if has_final != "1":
            in_progress = True
    if not fembs:
        in_progress = True

    qc_root = Path(settings.qc_root).resolve()
    return SessionMeta(
        session_id=_encode_session_id(rel_path),
        rel_path=rel_path,
        abs_path=qc_root / "Report" / rel_path,
        dir_name=run_dir,
        started_at=started_at,
        test_type_hint=hint,
        fembs=fembs,
        in_progress=in_progress,
    )


async def _remote_list_sessions(month: str | None) -> dict:
    """One-ssh-roundtrip listing of the remote tree (or one month)."""
    host = settings.remote_host
    cmd = _build_remote_list_cmd(month)
    output = await ssh_helper.ssh_run(host, cmd, timeout=20.0)
    by_run = _parse_remote_list(output)

    metas: list[SessionMeta] = []
    for rel, femb_map in by_run.items():
        metas.append(_meta_from_remote(rel, femb_map))

    # Group by month
    by_month: dict[str, list[SessionMeta]] = {}
    for m in metas:
        time_dir = m.rel_path.split("/", 1)[0]
        by_month.setdefault(time_dir, []).append(m)
    for runs in by_month.values():
        runs.sort(key=lambda mm: mm.started_at or "", reverse=True)

    if month is not None:
        return {"name": month, "runs": [_run_to_dict(m) for m in by_month.get(month, [])]}

    months = [
        {"name": k, "runs": [_run_to_dict(m) for m in v]}
        for k, v in sorted(by_month.items(), key=lambda kv: kv[0], reverse=True)
    ]
    return {"months": months}


async def list_sessions(month: str | None = None) -> dict:
    """Return the /monitor sessions tree (or one month's runs if `month` given).

    When `REMOTE_HOST` is set, the remote tree is fetched in one ssh roundtrip;
    on failure, falls back to local-disk scan with `from_local_cache: true` on
    each run. When `REMOTE_HOST` is blank, behaves exactly like #64 (local scan).

    Each response also carries a `remote` object describing connectivity, used
    by the frontend connectivity chip.
    """
    if month is not None and not TIME_DIR_RE.match(month):
        # Invalid month → empty (no remote call).
        return {"name": month, "runs": [], "remote": {"configured": bool(settings.remote_host)}}

    host = settings.remote_host
    if not host:
        out = _local_list_sessions(month, from_local_cache=False)
        out["remote"] = {"configured": False}
        return out

    try:
        out = await _remote_list_sessions(month)
        out["remote"] = {"configured": True, "ok": True, "host": host}
        return out
    except ssh_helper.RemoteError as e:
        out = _local_list_sessions(month, from_local_cache=True)
        out["remote"] = {
            "configured": True,
            "ok": False,
            "host": host,
            "error": str(e),
        }
        return out


def get_session(session_id: str) -> SessionMeta | None:
    qc_root = Path(settings.qc_root).resolve()
    try:
        rel_path = _decode_session_id(session_id)
    except Exception:
        return None
    abs_path = (qc_root / "Report" / rel_path).resolve()
    # safety: must be under qc_root/Report
    try:
        abs_path.relative_to(qc_root / "Report")
    except ValueError:
        return None
    if not abs_path.is_dir():
        return None
    return _build_session_meta(rel_path, abs_path)


_MD_IMG_RE = re.compile(r"(!\[[^\]]*\]\()([^)\s]+)(\))")
_HTML_IMG_RE = re.compile(
    r'(<img\b[^>]*?\bsrc\s*=\s*["\'])([^"\']+)(["\'])',
    re.IGNORECASE,
)


def _rewrite_md_image_urls(md: str, asset_base: str) -> str:
    """Rewrite both Markdown `![alt](path.png)` and HTML `<img src="path.png">`
    image references so relative paths resolve via the backend asset endpoint
    instead of the page URL. Absolute URLs and data: URIs pass through.
    """
    def sub(m: re.Match) -> str:
        head, url, tail = m.group(1), m.group(2).strip(), m.group(3)
        if url.startswith(("http://", "https://", "/", "data:")):
            return m.group(0)
        return f"{head}{asset_base}/{url}{tail}"
    md = _MD_IMG_RE.sub(sub, md)
    md = _HTML_IMG_RE.sub(sub, md)
    return md


async def get_report_md(
    session_id: str, femb_id: str, test_id: str
) -> dict | None:
    """Return the raw markdown for a single report file, or None if not found.

    Shape: {"test_id", "status": "pass"|"fail", "filename", "md"}.
    `femb_id` is "S0" / "S1"; `test_id` is "t1".."t17". Relative image refs
    in the markdown are rewritten to point at the asset endpoint so the
    embedded `.png` plots load from the local mirror.
    """
    meta = get_session(session_id)
    if meta is None:
        return None
    femb = next((f for f in meta.fembs if f.femb_id == femb_id), None)
    if femb is None:
        return None
    if not test_id.startswith("t") or not test_id[1:].isdigit():
        return None
    t_num = int(test_id[1:])
    slot = femb_id.lstrip("S")
    femb_dir = meta.abs_path / femb.subdir
    if not femb_dir.is_dir():
        return None
    for p in femb_dir.iterdir():
        m = REPORT_RE.match(p.name)
        if not m:
            continue
        if int(m.group(1)) != t_num or m.group(3) != slot:
            continue
        status = "pass" if m.group(2) == "P" else "fail"
        try:
            md = await monitor_sync.stable_read_text(p)
        except Exception:
            return None
        asset_base = f"/monitor/sessions/{session_id}/femb/{femb_id}/assets"
        md = _rewrite_md_image_urls(md, asset_base)
        return {
            "test_id": test_id,
            "status": status,
            "filename": p.name,
            "md": md,
        }
    return None


def get_report_asset_path(
    session_id: str, femb_id: str, filename: str
) -> Path | None:
    """Resolve `filename` (which may be a relative path with sub-dirs) to a
    file under the FEMB subdir of the local mirror. Rejects backslashes and
    any resolved path that escapes the FEMB subdir. Returns None if not found.
    """
    if not filename or "\\" in filename:
        return None
    meta = get_session(session_id)
    if meta is None:
        return None
    femb = next((f for f in meta.fembs if f.femb_id == femb_id), None)
    if femb is None:
        return None
    femb_root = (meta.abs_path / femb.subdir).resolve()
    p = (femb_root / filename).resolve()
    try:
        p.relative_to(femb_root)
    except ValueError:
        return None
    if not p.is_file():
        return None
    return p


# ─── Watcher: bridge watchdog → asyncio.Queue ──────────────────────────────

class _AsyncEventBridge(FileSystemEventHandler):
    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue):
        self.loop = loop
        self.queue = queue
        self._last_seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def _emit(self, path: str, kind: str) -> None:
        # Debounce per-path; drop duplicates within DEBOUNCE_S
        now = self.loop.time() if self.loop.is_running() else 0.0
        with self._lock:
            last = self._last_seen.get(path, 0.0)
            if now - last < DEBOUNCE_S:
                return
            self._last_seen[path] = now
        try:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, (path, kind))
        except RuntimeError:
            pass  # loop closed during shutdown

    def on_created(self, ev: FileSystemEvent) -> None:
        if not ev.is_directory:
            self._emit(str(ev.src_path), "created")

    def on_modified(self, ev: FileSystemEvent) -> None:
        # On some platforms a new file fires modified before/after created.
        if not ev.is_directory:
            self._emit(str(ev.src_path), "modified")

    def on_moved(self, ev: FileSystemEvent) -> None:
        if not ev.is_directory:
            self._emit(str(getattr(ev, "dest_path", ev.src_path)), "moved")


def _classify_file(abs_path: Path, meta: SessionMeta) -> dict | None:
    """Return an SSE event payload if path matches a watched filename, else None."""
    try:
        rel = abs_path.relative_to(meta.abs_path)
    except ValueError:
        return None
    parts = rel.parts
    if len(parts) != 2:
        return None
    femb_subdir, fname = parts

    femb = next((f for f in meta.fembs if f.subdir == femb_subdir), None)
    if femb is None:
        return None

    m = REPORT_RE.match(fname)
    if m:
        return {
            "type": "test_pass" if m.group(2) == "P" else "test_fail",
            "femb_id": femb.femb_id,
            "test_id": f"t{int(m.group(1))}",
            "file": str(rel),
        }
    if FINAL_RE.match(fname):
        return {
            "type": "final_report",
            "femb_id": femb.femb_id,
            "file": str(rel),
        }
    return None


def _existing_events(meta: SessionMeta) -> list[dict]:
    """Snapshot of events for files already on disk, in canonical order."""
    out: list[tuple[int, dict]] = []
    for femb in meta.fembs:
        femb_dir = meta.abs_path / femb.subdir
        if not femb_dir.is_dir():
            continue
        finals: list[dict] = []
        for f in femb_dir.iterdir():
            if not f.is_file():
                continue
            payload = _classify_file(f.resolve(), meta)
            if payload is None:
                continue
            if payload["type"] == "final_report":
                finals.append(payload)
            else:
                t = int(payload["test_id"].lstrip("t"))
                out.append((t, payload))
        for fin in finals:
            out.append((9999, fin))  # finals sort to the end per FEMB
    out.sort(key=lambda x: x[0])
    return [p for _, p in out]


def _all_fembs_finalized(meta: SessionMeta) -> bool:
    if not meta.fembs:
        return False
    return all(_has_final_report(meta.abs_path / f.subdir) for f in meta.fembs)


def _local_is_complete_and_persisted(rel_path: str) -> bool:
    """True iff the local mirror has Final_Report for every FEMB AND the DB
    has a femb_run row per FEMB for this session — i.e. the run is fully
    cached and there's nothing to fetch from remote. Lets watch_session skip
    the ssh pre-flight + rsync no-op on reselects of finished runs.
    """
    qc_root = Path(settings.qc_root).resolve()
    abs_path = (qc_root / "Report" / rel_path).resolve()
    if not abs_path.is_dir():
        return False
    meta = _build_session_meta(rel_path, abs_path)
    if meta is None or not meta.fembs or not _all_fembs_finalized(meta):
        return False
    sess_row = monitor_db.store.get_session_by_rel_path(rel_path)
    if not sess_row:
        return False
    runs = monitor_db.store.list_femb_runs(sess_row["id"])
    return len(runs) == len(meta.fembs)


async def _spawn_diagnostic(
    out: asyncio.Queue,
    meta: SessionMeta,
    payload: dict,
) -> None:
    """Background task: run the diagnostic for one failed report, push events to `out`."""
    femb_id = payload["femb_id"]
    test_id = payload["test_id"]
    femb = next((f for f in meta.fembs if f.femb_id == femb_id), None)
    md_path = meta.abs_path / payload["file"]
    try:
        md_text = await monitor_sync.stable_read_text(md_path)
    except Exception as exc:
        await out.put({
            "type": "diagnostic_error",
            "femb_id": femb_id,
            "test_id": test_id,
            "message": f"failed to read report: {exc}",
        })
        return

    await out.put({"type": "diagnostic_start", "femb_id": femb_id, "test_id": test_id})
    try:
        async for evt in run_diagnostic_for_failed_report(
            md_text=md_text,
            test_id=test_id,
            femb_id=femb_id,
            femb_serial=femb.serial if femb else "",
            test_type_hint=meta.test_type_hint,
        ):
            await out.put(evt)
    except Exception as exc:
        await out.put({
            "type": "diagnostic_error",
            "femb_id": femb_id,
            "test_id": test_id,
            "message": str(exc),
        })
    finally:
        await out.put({"type": "diagnostic_done", "femb_id": femb_id, "test_id": test_id})


async def _sync_status_poller(rel_path: str, out: asyncio.Queue) -> None:
    """Watches the shared SyncTaskState for `rel_path` and pushes a
    `sync_status` event on every transition of (cycle_failures, stalled,
    last_cycle_ok), plus a `sync_loop_done` event when the loop exits.
    """
    prev = None
    while True:
        state = monitor_sync.get_state(rel_path)
        if state is None:
            return
        snapshot = (state.cycle_failures, state.stalled, state.last_cycle_ok)
        if snapshot != prev:
            await out.put({
                "type": "sync_status",
                "cycle_failures": state.cycle_failures,
                "stalled": state.stalled,
                "ok": state.last_cycle_ok,
                "error": "" if state.last_cycle_ok else state.last_error,
            })
            prev = snapshot
        if state.done:
            await out.put({
                "type": "sync_loop_done",
                "reason": state.done_reason,
            })
            return
        await asyncio.sleep(1.0)


async def _file_producer(meta: SessionMeta, out: asyncio.Queue) -> None:
    """Push test_pass / test_fail / final_report payloads onto `out`."""
    seen_paths: set[str] = set()

    async def _flush_disk_state() -> None:
        """Scan the run dir and push any matching files not yet seen.

        Called on both startup (replay) and on the all-finalized exit path
        to guarantee Final_Reports written between watchdog polls are still
        delivered to the consumer.
        """
        for payload in _existing_events(meta):
            if payload["file"] in seen_paths:
                continue
            seen_paths.add(payload["file"])
            await out.put(payload)

    await _flush_disk_state()

    if _all_fembs_finalized(meta):
        return

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
    handler = _AsyncEventBridge(loop, queue)
    observer = Observer()
    observer.schedule(handler, str(meta.abs_path), recursive=True)
    observer.start()

    try:
        while True:
            try:
                abs_str, _ = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                if _all_fembs_finalized(meta):
                    # Belt-and-suspenders: emit any files the watchdog hasn't
                    # surfaced yet (race between the FS scan and the kernel
                    # event delivery) BEFORE exiting.
                    await _flush_disk_state()
                    return
                continue

            payload = _classify_file(Path(abs_str), meta)
            if payload is None or payload["file"] in seen_paths:
                continue
            seen_paths.add(payload["file"])
            await out.put(payload)

            if payload["type"] == "final_report" and _all_fembs_finalized(meta):
                # Same guarantee on the natural exit path.
                await _flush_disk_state()
                return
    finally:
        observer.stop()
        try:
            await asyncio.to_thread(observer.join, 2.0)
        except Exception:
            pass


def _is_placeholder_summary(md: str | None) -> bool:
    return bool(md) and md.startswith("_generating")


def _write_placeholder_row(
    meta: SessionMeta,
    femb_id: str,
    test_results: dict[str, str],
    diag_chunks: dict[str, list[str]],
) -> tuple[int, int]:
    """Synchronously write a placeholder femb_runs row.

    Called from the main loop on final_report — BEFORE the finalize task is
    spawned, so it lands even if every subsequent await is cancelled.
    Returns (session_db_id, femb_run_id).
    """
    femb = next((f for f in meta.fembs if f.femb_id == femb_id), None)
    serial = femb.serial if femb else ""
    failed_tests = sorted(
        (tid for tid, v in test_results.items() if v == "fail"),
        key=lambda t: int(t.lstrip("t")) if t.lstrip("t").isdigit() else 0,
    )
    n_tests = len(test_results)
    n_failed = len(failed_tests)
    passed = n_failed == 0
    diagnostic_md = "\n\n---\n\n".join(
        f"### {tid}\n\n{''.join(diag_chunks.get(tid, []))}".strip()
        for tid in failed_tests if tid in diag_chunks
    )
    session_db_id = monitor_db.store.upsert_session(meta.rel_path, meta.started_at)
    # Don't overwrite an already-final summary if the row exists from a prior good run.
    existing = monitor_db.store.get_femb_run(session_db_id, femb_id)
    if (
        existing
        and (existing.get("summary_md") or "").strip()
        and not _is_placeholder_summary(existing.get("summary_md"))
    ):
        return session_db_id, existing["id"]
    femb_run_id = monitor_db.store.upsert_femb_run(
        session_id=session_db_id,
        femb_id=femb_id,
        femb_serial=serial,
        n_tests=n_tests,
        n_failed=n_failed,
        passed=passed,
        summary_md="_generating summary…_",
        diagnostic_md=diagnostic_md,
    )
    return session_db_id, femb_run_id


async def _finalize_femb(
    out: asyncio.Queue,
    meta: SessionMeta,
    femb_id: str,
    final_report_rel: str,
    test_results: dict[str, str],
    diag_chunks: dict[str, list[str]],
    diag_tasks_for_femb: set[asyncio.Task],
) -> None:
    """Persist + summarise one FEMB's completed run.

    Writes a placeholder DB row IMMEDIATELY (synchronously) so the fast-path
    on session re-select works even if this task is cancelled mid-stream.
    """
    femb = next((f for f in meta.fembs if f.femb_id == femb_id), None)
    serial = femb.serial if femb else ""

    failed_tests = sorted(
        (tid for tid, v in test_results.items() if v == "fail"),
        key=lambda t: int(t.lstrip("t")) if t.lstrip("t").isdigit() else 0,
    )
    n_tests = len(test_results)
    n_failed = len(failed_tests)
    passed = n_failed == 0

    def _build_diagnostic_md() -> str | None:
        return "\n\n---\n\n".join(
            f"### {tid}\n\n{''.join(diag_chunks.get(tid, []))}".strip()
            for tid in failed_tests if tid in diag_chunks
        ) or None

    session_db_id = monitor_db.store.upsert_session(meta.rel_path, meta.started_at)
    existing = monitor_db.store.get_femb_run(session_db_id, femb_id)

    # Cached path: a previously-persisted row with a real (non-placeholder) summary.
    if (
        existing
        and (existing.get("summary_md") or "").strip()
        and not _is_placeholder_summary(existing.get("summary_md"))
    ):
        summary_md = existing["summary_md"]
        diagnostic_md = existing.get("diagnostic_md") or _build_diagnostic_md()
        femb_run_id = existing["id"]
        await out.put({
            "type": "femb_summary",
            "femb_id": femb_id,
            "femb_serial": serial,
            "n_tests": n_tests,
            "n_failed": n_failed,
            "passed": passed,
            "summary_md": summary_md,
            "from_cache": True,
            "femb_run_id": femb_run_id,
        })
        _maybe_complete_session(out, meta, session_db_id)
        return

    # Step 1: synchronous placeholder write — guaranteed to land even if every
    # subsequent await is cancelled.
    femb_run_id = monitor_db.store.upsert_femb_run(
        session_id=session_db_id,
        femb_id=femb_id,
        femb_serial=serial,
        n_tests=n_tests,
        n_failed=n_failed,
        passed=passed,
        summary_md="_generating summary…_",
        diagnostic_md=_build_diagnostic_md() or "",
    )

    # Step 2: wait for pending diag tasks to finish; if cancelled, the placeholder
    # still exists. Re-raise so watch_session's cleanup proceeds.
    if diag_tasks_for_femb:
        await asyncio.gather(*diag_tasks_for_femb, return_exceptions=True)

    # Refresh diagnostic_md now that diag tasks have all flushed.
    diagnostic_md = _build_diagnostic_md()
    monitor_db.store.upsert_femb_run(
        session_id=session_db_id,
        femb_id=femb_id,
        femb_serial=serial,
        n_tests=n_tests,
        n_failed=n_failed,
        passed=passed,
        summary_md="_generating summary…_",
        diagnostic_md=diagnostic_md or "",
    )

    final_md = ""
    try:
        full = meta.abs_path / final_report_rel
        final_md = await monitor_sync.stable_read_text(full)
    except Exception:
        pass

    await out.put({
        "type": "femb_summary_start",
        "femb_id": femb_id,
        "femb_serial": serial,
        "n_tests": n_tests,
        "n_failed": n_failed,
        "passed": passed,
    })

    parts: list[str] = []
    cancelled = False
    try:
        async for tok in stream_femb_summary(
            femb_id=femb_id,
            femb_serial=serial,
            test_type_hint=meta.test_type_hint,
            n_tests=n_tests,
            n_failed=n_failed,
            passed=passed,
            failed_tests=failed_tests,
            final_report_md=final_md,
        ):
            parts.append(tok)
            await out.put({
                "type": "femb_summary_token",
                "femb_id": femb_id,
                "text": tok,
            })
        summary_md = "".join(parts).strip() or "_(empty summary)_"
    except asyncio.CancelledError:
        summary_md = (
            "".join(parts).strip()
            or "_generation cancelled — use ‘regenerate’ to retry_"
        )
        cancelled = True
    except Exception as exc:
        summary_md = f"_summary generation failed: {exc}_"

    # Step 4: persist whatever we ended up with (synchronous — runs even on cancel).
    monitor_db.store.upsert_femb_run(
        session_id=session_db_id,
        femb_id=femb_id,
        femb_serial=serial,
        n_tests=n_tests,
        n_failed=n_failed,
        passed=passed,
        summary_md=summary_md,
        diagnostic_md=diagnostic_md or "",
    )

    if cancelled:
        raise asyncio.CancelledError()

    await out.put({
        "type": "femb_summary",
        "femb_id": femb_id,
        "femb_serial": serial,
        "n_tests": n_tests,
        "n_failed": n_failed,
        "passed": passed,
        "summary_md": summary_md,
        "from_cache": False,
        "femb_run_id": femb_run_id,
    })

    _maybe_complete_session(out, meta, session_db_id)


def _maybe_complete_session(out: asyncio.Queue, meta: SessionMeta, session_db_id: int) -> None:
    """If every FEMB has a non-placeholder row, mark the session complete."""
    runs = monitor_db.store.list_femb_runs(session_db_id)
    if not meta.fembs or len(runs) < len(meta.fembs):
        return
    if any(_is_placeholder_summary(r.get("summary_md")) for r in runs):
        return
    overall_passed = all(r.get("passed") for r in runs)
    finished_at = datetime.now(timezone.utc).isoformat()
    monitor_db.store.complete_session(session_db_id, finished_at, overall_passed)
    try:
        out.put_nowait({
            "type": "session_complete",
            "finished_at": finished_at,
            "overall_passed": overall_passed,
        })
    except asyncio.QueueFull:
        pass  # unbounded queue, won't actually hit


_FAIL_REPORT_RE = re.compile(r"^report_FEMB_\d+_t(\d+)_F_S\d+\.md$")
_DIAG_SECTION_RE = re.compile(r"^### (t\d+)\s*\n+(.*)$", re.DOTALL)


async def regenerate_diagnostic_stream(
    femb_run_id: int,
    only_test_id: str | None = None,
) -> AsyncIterator[str]:
    """Re-run the diagnostic agent for failed tests of one FEMB run.

    If `only_test_id` is given, regen just that one section and merge into the
    existing diagnostic_md; otherwise regen all failures (overwrite).
    Streams the same diagnostic_* events as the live flow plus a final
    regenerate_complete event, updates femb_runs.diagnostic_md on success.
    """
    conn = monitor_db.store._open()
    try:
        row = conn.execute(
            "SELECT fr.id, fr.session_id, fr.femb_id, fr.femb_serial, fr.diagnostic_md, fs.run_dir "
            "FROM femb_runs fr JOIN femb_sessions fs ON fs.id = fr.session_id "
            "WHERE fr.id = ?",
            (femb_run_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        yield event({"type": "error", "message": "femb run not found"})
        yield DONE
        return

    femb_id = row["femb_id"]
    femb_serial = row["femb_serial"]
    rel_run_dir = row["run_dir"]
    existing_md = row["diagnostic_md"] or ""

    qc_root = Path(settings.qc_root).resolve()
    run_dir_abs = (qc_root / "Report" / rel_run_dir).resolve()
    femb_subdir = run_dir_abs / f"FEMB{femb_serial}_{femb_id}"

    if not femb_subdir.is_dir():
        yield event({"type": "error", "message": f"FEMB directory not found: {femb_subdir.name}"})
        yield DONE
        return

    # Parse the run dir name for the test_type_hint, tolerant of unknown formats.
    parent = Path(rel_run_dir).parent.name
    started_at = None
    test_type_hint = run_dir_abs.name
    parsed = _parse_time_parent(parent)
    if parsed is not None:
        started_at, test_type_hint = _parse_run_dir_name(run_dir_abs.name, *parsed)
    _ = started_at  # only test_type_hint is needed here

    failed: list[tuple[int, Path]] = []
    for p in femb_subdir.iterdir():
        if not p.is_file():
            continue
        m = _FAIL_REPORT_RE.match(p.name)
        if m:
            failed.append((int(m.group(1)), p))
    failed.sort(key=lambda x: x[0])
    if only_test_id:
        target = only_test_id.lstrip("t")
        failed = [(n, p) for n, p in failed if str(n) == target]
    failed_files = [p for _, p in failed]

    yield event({
        "type": "regenerate_start",
        "femb_run_id": femb_run_id,
        "femb_id": femb_id,
        "n_failures": len(failed_files),
        "test_id": only_test_id,
    })

    new_sections: dict[str, str] = {}
    for f in failed_files:
        m = _FAIL_REPORT_RE.match(f.name)
        if m is None:
            continue
        test_id = f"t{int(m.group(1))}"
        try:
            md_text = await monitor_sync.stable_read_text(f)
        except Exception as exc:
            yield event({
                "type": "diagnostic_error",
                "femb_id": femb_id,
                "test_id": test_id,
                "message": f"failed to read report: {exc}",
            })
            continue

        yield event({"type": "diagnostic_start", "femb_id": femb_id, "test_id": test_id})
        tokens: list[str] = []
        try:
            from diagnostic_agent import run_diagnostic_for_failed_report  # local import to avoid cycle at module load
            async for evt in run_diagnostic_for_failed_report(
                md_text=md_text,
                test_id=test_id,
                femb_id=femb_id,
                femb_serial=femb_serial,
                test_type_hint=test_type_hint,
            ):
                yield event(evt)
                if evt.get("type") == "diagnostic_token":
                    tokens.append(evt.get("text", ""))
        except Exception as exc:
            yield event({
                "type": "diagnostic_error",
                "femb_id": femb_id,
                "test_id": test_id,
                "message": str(exc),
            })
        yield event({"type": "diagnostic_done", "femb_id": femb_id, "test_id": test_id})

        if tokens:
            new_sections[test_id] = "".join(tokens).strip()

    if only_test_id:
        # Merge: keep existing sections except the targeted one(s) we just regen'd.
        merged = dict(_parse_diagnostic_md(existing_md))
        merged.update(new_sections)
    else:
        # Overwrite: only the freshly-generated sections survive.
        merged = new_sections

    ordered = sorted(
        merged.items(),
        key=lambda kv: int(kv[0].lstrip("t")) if kv[0].lstrip("t").isdigit() else 0,
    )
    new_diagnostic_md = "\n\n---\n\n".join(f"### {tid}\n\n{text}" for tid, text in ordered)
    monitor_db.store.update_diagnostic(femb_run_id, new_diagnostic_md or None)

    yield event({
        "type": "regenerate_complete",
        "femb_run_id": femb_run_id,
        "femb_id": femb_id,
        "test_id": only_test_id,
        "diagnostic_md": new_diagnostic_md,
    })
    yield DONE





def _parse_diagnostic_md(md: str) -> list[tuple[str, str]]:
    """Split a saved diagnostic_md back into ordered [(test_id, text), ...]."""
    if not md or not md.strip():
        return []
    out: list[tuple[str, str]] = []
    for chunk in re.split(r"\n\s*---\s*\n", md):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = _DIAG_SECTION_RE.match(chunk)
        if m:
            out.append((m.group(1), m.group(2).strip()))
    return out


async def _replay_persisted(
    meta: SessionMeta,
    session_db_id: int,
    runs: list[dict],
) -> AsyncIterator[str]:
    """Yield SSE events for a finished session whose state is in the DB.

    Diagnostics are always replayed from DB (no LLM). FEMBs whose summary_md
    is still a placeholder (interrupted previously) get a fresh streaming
    summary; FEMBs with real summaries emit them as cached.
    """
    for payload in _existing_events(meta):
        yield event(payload)

    runs_by_femb = {r["femb_id"]: r for r in runs}

    # Replay cached diagnostics for every FEMB.
    for femb in meta.fembs:
        r = runs_by_femb.get(femb.femb_id)
        if not r:
            continue
        for test_id, text in _parse_diagnostic_md(r.get("diagnostic_md") or ""):
            yield event({
                "type": "diagnostic_start",
                "femb_id": femb.femb_id,
                "test_id": test_id,
                "cached": True,
            })
            yield event({
                "type": "diagnostic_token",
                "femb_id": femb.femb_id,
                "test_id": test_id,
                "text": text,
            })
            yield event({
                "type": "diagnostic_done",
                "femb_id": femb.femb_id,
                "test_id": test_id,
            })

    # Per-FEMB summary: cached or freshly streamed if placeholder.
    for femb in meta.fembs:
        r = runs_by_femb.get(femb.femb_id)
        if not r:
            continue
        if _is_placeholder_summary(r.get("summary_md")):
            async for chunk in _stream_summary_for_existing_row(meta, session_db_id, femb, r):
                yield chunk
        else:
            yield event({
                "type": "femb_summary",
                "femb_id": femb.femb_id,
                "femb_serial": r.get("femb_serial") or femb.serial,
                "n_tests": r.get("n_tests", 0),
                "n_failed": r.get("n_failed", 0),
                "passed": bool(r.get("passed")),
                "summary_md": r.get("summary_md") or "",
                "from_cache": True,
                "femb_run_id": r.get("id"),
            })

    # Check if the session should now be marked complete.
    refreshed = monitor_db.store.list_femb_runs(session_db_id)
    if (
        meta.fembs
        and len(refreshed) == len(meta.fembs)
        and not any(_is_placeholder_summary(r.get("summary_md")) for r in refreshed)
    ):
        db_session = monitor_db.store.get_session_by_rel_path(meta.rel_path)
        finished_at = (db_session and db_session.get("finished_at")) or None
        if not finished_at:
            finished_at = datetime.now(timezone.utc).isoformat()
            overall = all(r.get("passed") for r in refreshed)
            monitor_db.store.complete_session(session_db_id, finished_at, overall)
            yield event({
                "type": "session_complete",
                "finished_at": finished_at,
                "overall_passed": overall,
            })
        elif db_session:
            yield event({
                "type": "session_complete",
                "finished_at": finished_at,
                "overall_passed": bool(db_session.get("overall_passed")),
            })


async def _stream_summary_for_existing_row(
    meta: SessionMeta,
    session_db_id: int,
    femb: FembInfo,
    row: dict,
) -> AsyncIterator[str]:
    """Replace a placeholder summary by streaming a fresh one and updating the DB row."""
    femb_id = femb.femb_id
    serial = row.get("femb_serial") or femb.serial
    n_tests = row.get("n_tests", 0)
    n_failed = row.get("n_failed", 0)
    passed = bool(row.get("passed"))
    diagnostic_md = row.get("diagnostic_md") or ""

    # Derive failed-test IDs from the saved diagnostic_md (its sections are
    # one-per-failure). Falls back to no list if md is empty.
    failed_tests = [tid for tid, _ in _parse_diagnostic_md(diagnostic_md)]

    final_md = ""
    final_path = None
    femb_dir = meta.abs_path / femb.subdir
    if femb_dir.is_dir():
        for p in femb_dir.iterdir():
            if FINAL_RE.match(p.name):
                final_path = p
                break
    if final_path is not None:
        try:
            final_md = await monitor_sync.stable_read_text(final_path)
        except Exception:
            pass

    yield event({
        "type": "femb_summary_start",
        "femb_id": femb_id,
        "femb_serial": serial,
        "n_tests": n_tests,
        "n_failed": n_failed,
        "passed": passed,
    })

    parts: list[str] = []
    cancelled = False
    try:
        async for tok in stream_femb_summary(
            femb_id=femb_id,
            femb_serial=serial,
            test_type_hint=meta.test_type_hint,
            n_tests=n_tests,
            n_failed=n_failed,
            passed=passed,
            failed_tests=failed_tests,
            final_report_md=final_md,
        ):
            parts.append(tok)
            yield event({
                "type": "femb_summary_token",
                "femb_id": femb_id,
                "text": tok,
            })
        summary_md = "".join(parts).strip() or "_(empty summary)_"
    except asyncio.CancelledError:
        summary_md = (
            "".join(parts).strip()
            or "_generation cancelled — use ‘regenerate’ to retry_"
        )
        cancelled = True
    except Exception as exc:
        summary_md = f"_summary generation failed: {exc}_"

    monitor_db.store.upsert_femb_run(
        session_id=session_db_id,
        femb_id=femb_id,
        femb_serial=serial,
        n_tests=n_tests,
        n_failed=n_failed,
        passed=passed,
        summary_md=summary_md,
        diagnostic_md=diagnostic_md,
    )

    if cancelled:
        raise asyncio.CancelledError()

    yield event({
        "type": "femb_summary",
        "femb_id": femb_id,
        "femb_serial": serial,
        "n_tests": n_tests,
        "n_failed": n_failed,
        "passed": passed,
        "summary_md": summary_md,
        "from_cache": False,
        "femb_run_id": row.get("id"),
    })


async def watch_session(session_id: str, *, force_resync: bool = False) -> AsyncIterator[str]:
    """SSE generator: emits session_info, per-file events, per-failure diagnostic
    events (concurrent), per-FEMB summary on Final_Report, and session_complete
    when all FEMBs are persisted. Ends after the producer and all spawned tasks
    finish and the queue is drained.
    """
    # Remote mode: hand off to monitor_sync, which decides one-shot vs. loop
    # based on the remote's newest .md mtime (pre-flight 4 h staleness rule)
    # and shares the rsync task across all subscribers of this rel_path.
    #
    # Optimization: skip the remote round-trip entirely when the local mirror
    # already has Final_Report for every FEMB AND the DB has a row per FEMB.
    # That's the state of a fully-cached finished run — there's nothing to
    # fetch, and the existing fast-path replay below makes reselects instant.
    sync_rel_path: str | None = None
    sync_state: monitor_sync.SyncTaskState | None = None
    if settings.remote_host:
        try:
            sync_rel_path = _decode_session_id(session_id)
        except Exception:
            yield event({"type": "error", "message": "invalid session id"})
            yield DONE
            return
        if force_resync or not _local_is_complete_and_persisted(sync_rel_path):
            yield event({"type": "sync_start", "rel_path": sync_rel_path})
            sync_state = await monitor_sync.ensure_one_shot_or_loop(sync_rel_path)
            if sync_state.done_reason == "preflight_failed":
                yield event({
                    "type": "error",
                    "message": f"remote sync failed: {sync_state.last_error}",
                })
                yield DONE
                return
            yield event({
                "type": "sync_done",
                "looping": sync_state.task is not None and not sync_state.done,
                "reason": sync_state.done_reason,
            })

    meta = get_session(session_id)
    if meta is None:
        yield event({"type": "error", "message": "session not found"})
        yield DONE
        return

    # Pre-create session row (no-op if exists).
    session_db_id = monitor_db.store.upsert_session(meta.rel_path, meta.started_at)

    yield event({"type": "session_info", **meta.to_json(), "test_labels": TEST_LABELS})

    # Fast-path: every FEMB has a Final_Report on disk AND a DB row (diagnostics
    # are saved). Replay file events + cached diagnostics; if any row has a
    # placeholder summary (interrupted earlier), stream a fresh summary inline
    # rather than running the live-watch+diagnostic path again.
    if _all_fembs_finalized(meta) and meta.fembs:
        runs = monitor_db.store.list_femb_runs(session_db_id)
        if len(runs) == len(meta.fembs):
            async for sse_chunk in _replay_persisted(meta, session_db_id, runs):
                yield sse_chunk
            yield DONE
            return

    out: asyncio.Queue[dict] = asyncio.Queue()
    file_task = asyncio.create_task(_file_producer(meta, out))
    sync_status_task: asyncio.Task | None = None
    if sync_state is not None and sync_state.task is not None and not sync_state.done:
        sync_status_task = asyncio.create_task(
            _sync_status_poller(sync_rel_path, out)
        )
    diag_tasks: set[asyncio.Task] = set()
    finalize_tasks: set[asyncio.Task] = set()

    test_results: dict[str, dict[str, str]] = defaultdict(dict)
    diag_chunks: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    diag_tasks_by_femb: dict[str, set[asyncio.Task]] = defaultdict(set)
    finalized_fembs: set[str] = set()

    try:
        while True:
            diag_tasks = {t for t in diag_tasks if not t.done()}
            finalize_tasks = {t for t in finalize_tasks if not t.done()}
            if file_task.done() and not diag_tasks and not finalize_tasks and out.empty():
                break
            try:
                payload = await asyncio.wait_for(out.get(), timeout=0.2)
            except asyncio.TimeoutError:
                continue

            yield event(payload)

            ptype = payload.get("type")
            if ptype == "test_pass":
                test_results[payload["femb_id"]][payload["test_id"]] = "pass"
            elif ptype == "test_fail":
                test_results[payload["femb_id"]][payload["test_id"]] = "fail"
                dt = asyncio.create_task(_spawn_diagnostic(out, meta, payload))
                diag_tasks.add(dt)
                diag_tasks_by_femb[payload["femb_id"]].add(dt)
            elif ptype == "diagnostic_token":
                diag_chunks[payload["femb_id"]][payload["test_id"]].append(payload["text"])
            elif ptype == "final_report":
                femb_id = payload["femb_id"]
                if femb_id not in finalized_fembs:
                    finalized_fembs.add(femb_id)
                    # Persist a placeholder row synchronously BEFORE spawning the
                    # task, so the row exists even if the task is cancelled before
                    # it gets a chance to run.
                    _write_placeholder_row(
                        meta=meta,
                        femb_id=femb_id,
                        test_results=test_results[femb_id],
                        diag_chunks=diag_chunks[femb_id],
                    )
                    pending = {t for t in diag_tasks_by_femb[femb_id] if not t.done()}
                    ft = asyncio.create_task(_finalize_femb(
                        out=out,
                        meta=meta,
                        femb_id=femb_id,
                        final_report_rel=payload["file"],
                        test_results=dict(test_results[femb_id]),
                        diag_chunks=diag_chunks[femb_id],
                        diag_tasks_for_femb=pending,
                    ))
                    finalize_tasks.add(ft)
    except asyncio.CancelledError:
        raise
    finally:
        bg = [file_task, *diag_tasks, *finalize_tasks]
        if sync_status_task is not None:
            bg.append(sync_status_task)
        for t in bg:
            if not t.done():
                t.cancel()
        await asyncio.gather(*bg, return_exceptions=True)

    yield DONE

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
from config import settings
from diagnostic_agent import run_diagnostic_for_failed_report, summarize_femb_run
from sse import DONE, event

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

def list_sessions() -> list[dict]:
    """Scan $QC_ROOT/Report/Time_*/ and return parsed session metadata, newest first.
    Merges DB state (overall_passed, finished_at, persisted=True) where present.
    """
    qc_root = Path(settings.qc_root).resolve()
    report_root = qc_root / "Report"
    if not report_root.is_dir():
        return []

    out: list[SessionMeta] = []
    for time_dir in report_root.iterdir():
        if not time_dir.is_dir() or not TIME_DIR_RE.match(time_dir.name):
            continue
        for run_dir in time_dir.iterdir():
            if not run_dir.is_dir():
                continue
            rel = f"{time_dir.name}/{run_dir.name}"
            meta = _build_session_meta(rel, run_dir.resolve())
            if meta is not None:
                out.append(meta)

    # newest first by started_at (None last)
    out.sort(key=lambda m: m.started_at or "", reverse=True)
    result = []
    for m in out:
        d = m.to_json()
        db_row = monitor_db.store.get_session_by_rel_path(m.rel_path)
        if db_row:
            d["persisted"] = True
            d["overall_passed"] = bool(db_row.get("overall_passed"))
            d["finished_at"] = db_row.get("finished_at")
        else:
            d["persisted"] = False
        result.append(d)
    return result


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
        md_text = await asyncio.to_thread(md_path.read_text, encoding="utf-8")
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


async def _file_producer(meta: SessionMeta, out: asyncio.Queue) -> None:
    """Push test_pass / test_fail / final_report payloads onto `out`."""
    seen_paths: set[str] = set()

    for payload in _existing_events(meta):
        seen_paths.add(payload["file"])
        await out.put(payload)

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
                    return
                continue

            payload = _classify_file(Path(abs_str), meta)
            if payload is None or payload["file"] in seen_paths:
                continue
            seen_paths.add(payload["file"])
            await out.put(payload)

            if payload["type"] == "final_report" and _all_fembs_finalized(meta):
                return
    finally:
        observer.stop()
        try:
            await asyncio.to_thread(observer.join, 2.0)
        except Exception:
            pass


async def _finalize_femb(
    out: asyncio.Queue,
    meta: SessionMeta,
    femb_id: str,
    final_report_rel: str,
    test_results: dict[str, str],
    diag_chunks: dict[str, list[str]],
    diag_tasks_for_femb: set[asyncio.Task],
) -> None:
    """Wait for pending diagnostics for this FEMB, summarise, persist, emit."""
    if diag_tasks_for_femb:
        await asyncio.gather(*diag_tasks_for_femb, return_exceptions=True)

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
    ) or None

    session_db_id = monitor_db.store.upsert_session(meta.rel_path, meta.started_at)
    existing = monitor_db.store.get_femb_run(session_db_id, femb_id)

    if existing and (existing.get("summary_md") or "").strip():
        summary_md = existing["summary_md"]
        diagnostic_md = existing.get("diagnostic_md") or diagnostic_md
        from_cache = True
    else:
        final_md = ""
        try:
            full = meta.abs_path / final_report_rel
            final_md = await asyncio.to_thread(full.read_text, encoding="utf-8")
        except Exception:
            pass
        try:
            summary_md = await summarize_femb_run(
                femb_id=femb_id,
                femb_serial=serial,
                test_type_hint=meta.test_type_hint,
                n_tests=n_tests,
                n_failed=n_failed,
                passed=passed,
                failed_tests=failed_tests,
                final_report_md=final_md,
            )
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
            diagnostic_md=diagnostic_md or "",
        )
        from_cache = False

    await out.put({
        "type": "femb_summary",
        "femb_id": femb_id,
        "femb_serial": serial,
        "n_tests": n_tests,
        "n_failed": n_failed,
        "passed": passed,
        "summary_md": summary_md,
        "from_cache": from_cache,
    })

    # If every FEMB in this session is now persisted, complete the session.
    runs = monitor_db.store.list_femb_runs(session_db_id)
    if len(runs) >= len(meta.fembs) and meta.fembs:
        overall_passed = all(r.get("passed") for r in runs)
        finished_at = datetime.now(timezone.utc).isoformat()
        monitor_db.store.complete_session(session_db_id, finished_at, overall_passed)
        await out.put({
            "type": "session_complete",
            "finished_at": finished_at,
            "overall_passed": overall_passed,
        })


async def watch_session(session_id: str) -> AsyncIterator[str]:
    """SSE generator: emits session_info, per-file events, per-failure diagnostic
    events (concurrent), per-FEMB summary on Final_Report, and session_complete
    when all FEMBs are persisted. Ends after the producer and all spawned tasks
    finish and the queue is drained.
    """
    meta = get_session(session_id)
    if meta is None:
        yield event({"type": "error", "message": "session not found"})
        yield DONE
        return

    # Pre-create session row (no-op if exists).
    monitor_db.store.upsert_session(meta.rel_path, meta.started_at)

    yield event({"type": "session_info", **meta.to_json()})

    out: asyncio.Queue[dict] = asyncio.Queue()
    file_task = asyncio.create_task(_file_producer(meta, out))
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
        for t in [file_task, *diag_tasks, *finalize_tasks]:
            if not t.done():
                t.cancel()
        await asyncio.gather(file_task, *diag_tasks, *finalize_tasks, return_exceptions=True)

    yield DONE

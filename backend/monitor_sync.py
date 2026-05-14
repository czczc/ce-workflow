"""Live rsync loop for /monitor.

When a user selects a remote session, this module decides — based on the
newest remote `.md` mtime — whether the run is "still going" or stale:

  * stale (newest .md older than sync_preflight_stale_hours)  → one-shot rsync, done.
  * fresh                                                     → start a per-rel_path
    asyncio task that rsyncs every sync_interval_sec until either all FEMBs
    have Final_Reports locally or sync_idle_timeout_min minutes pass without a
    newer .md appearing.

A single task per rel_path is shared across all SSE subscribers. The task
outlives any individual subscriber: if the user closes the tab mid-watch the
mirror continues to fill until its own stop condition fires.

The state object carries enough fields for callers (watch_session) to derive
chip transitions: cycle_failures counts consecutive rsync failures; `stalled`
flips on at 3+; `last_cycle_ok` is the most-recent cycle outcome.
"""

from __future__ import annotations

import asyncio
import shlex
import time
from dataclasses import dataclass, field
from pathlib import Path

import ssh_helper
from config import settings


@dataclass
class SyncTaskState:
    rel_path: str
    started_at: float = field(default_factory=time.time)
    task: asyncio.Task | None = None
    first_cycle_done: asyncio.Event = field(default_factory=asyncio.Event)

    # Cycle health
    cycle_failures: int = 0
    last_cycle_ok: bool = True
    last_cycle_at: float = 0.0
    last_error: str = ""
    stalled: bool = False  # 3+ consecutive failures

    # Termination tracking
    last_mtime_seen: float = 0.0  # newest .md mtime observed (epoch s)
    done: bool = False
    done_reason: str = ""  # "one_shot" | "finalized" | "idle_timeout" | "preflight_failed" | "cancelled"


_tasks: dict[str, SyncTaskState] = {}
_tasks_lock = asyncio.Lock()


# ─── Remote / local probes ─────────────────────────────────────────────────

async def _remote_newest_md_mtime(rel_path: str) -> float | None:
    """Newest `.md` mtime (epoch seconds) under the remote run dir, or None
    if the directory is empty / missing. Raises RemoteError on ssh failure.
    """
    root = shlex.quote(settings.remote_qc_root.rstrip("/"))
    rel = shlex.quote(rel_path)
    cmd = (
        f"cd {root}/Report/{rel} 2>/dev/null || exit 0; "
        f"find . -name '*.md' -printf '%T@\\n' 2>/dev/null | sort -n | tail -1"
    )
    out = await ssh_helper.ssh_run(settings.remote_host, cmd, timeout=15.0)
    out = out.strip()
    if not out:
        return None
    try:
        return float(out)
    except ValueError:
        return None


def _local_newest_md_mtime(rel_path: str) -> float:
    """Max mtime of any locally-mirrored `.md` file under the run dir.
    Returns 0.0 if the dir is missing or empty.
    """
    local_dir = Path(settings.qc_root).resolve() / "Report" / rel_path
    if not local_dir.is_dir():
        return 0.0
    newest = 0.0
    for p in local_dir.rglob("*.md"):
        try:
            mtime = p.stat().st_mtime
            if mtime > newest:
                newest = mtime
        except OSError:
            pass
    return newest


def _local_all_fembs_finalized(rel_path: str) -> bool:
    """True iff the local mirror contains at least one FEMB subdir and every
    FEMB subdir has a Final_Report_*.md file.
    """
    local_dir = Path(settings.qc_root).resolve() / "Report" / rel_path
    if not local_dir.is_dir():
        return False
    saw_femb = False
    for entry in local_dir.iterdir():
        if not entry.is_dir():
            continue
        saw_femb = True
        has_final = any(
            p.is_file() and p.name.startswith("Final_Report_") and p.suffix == ".md"
            for p in entry.iterdir()
        )
        if not has_final:
            return False
    return saw_femb


# ─── Loop body & registry ──────────────────────────────────────────────────

async def _do_rsync(state: SyncTaskState) -> None:
    """One rsync cycle. Updates state.cycle_failures / stalled / last_cycle_ok."""
    host = settings.remote_host
    remote_path = f"{settings.remote_qc_root.rstrip('/')}/Report/{state.rel_path}"
    local_path = Path(settings.qc_root).resolve() / "Report" / state.rel_path
    try:
        await ssh_helper.rsync_pull(host, remote_path, local_path, md_only=True)
        state.cycle_failures = 0
        state.last_cycle_ok = True
        state.stalled = False
        state.last_error = ""
    except ssh_helper.RemoteError as e:
        state.cycle_failures += 1
        state.last_cycle_ok = False
        state.last_error = str(e)
        if state.cycle_failures >= 3:
            state.stalled = True
    finally:
        state.last_cycle_at = time.time()


async def _sync_loop(state: SyncTaskState) -> None:
    """Persistent loop body. Persists past SSE-subscriber disconnect; ends only
    on Final_Reports locally, idle timeout, or task cancellation.
    """
    interval = max(1, settings.sync_interval_sec)
    idle_timeout = max(60, settings.sync_idle_timeout_min * 60)
    try:
        while not state.done:
            await _do_rsync(state)
            state.first_cycle_done.set()

            # Termination: all FEMBs have a Final_Report locally.
            if _local_all_fembs_finalized(state.rel_path):
                state.done_reason = "finalized"
                break

            # Idle timeout: only counts once we've seen at least one .md.
            newest = _local_newest_md_mtime(state.rel_path)
            if newest > state.last_mtime_seen:
                state.last_mtime_seen = newest
            if (
                state.last_mtime_seen > 0
                and (time.time() - state.last_mtime_seen) > idle_timeout
            ):
                state.done_reason = "idle_timeout"
                break

            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        state.done_reason = state.done_reason or "cancelled"
        raise
    finally:
        state.done = True
        state.first_cycle_done.set()
        asyncio.create_task(_retire_task(state.rel_path, delay=30.0))


async def _retire_task(rel_path: str, *, delay: float) -> None:
    """Remove a finished task from the registry after a grace period so that
    late-arriving subscribers can still read the final state.
    """
    await asyncio.sleep(delay)
    async with _tasks_lock:
        existing = _tasks.get(rel_path)
        if existing is not None and existing.done:
            _tasks.pop(rel_path, None)


# ─── Public API ────────────────────────────────────────────────────────────

async def ensure_one_shot_or_loop(rel_path: str) -> SyncTaskState:
    """Make sure a sync is running (or finished) for `rel_path` and return the
    shared SyncTaskState. Blocks until at least one rsync cycle has completed
    (so the caller is guaranteed files-on-disk before reading), or until the
    one-shot path returns.

    Caller's contract: read `state.cycle_failures` / `state.stalled` / etc.
    after this returns; the loop (if running) continues to update them in the
    background.
    """
    if not settings.remote_host:
        return SyncTaskState(rel_path=rel_path, done=True, done_reason="no_remote")

    async with _tasks_lock:
        existing = _tasks.get(rel_path)
        if existing is not None:
            # Subscriber attaching to an in-flight or recently-finished task.
            await_existing = existing
        else:
            await_existing = None

        if await_existing is None:
            state = SyncTaskState(rel_path=rel_path)
            _tasks[rel_path] = state
        else:
            state = await_existing

    if await_existing is not None:
        # Wait for at least one cycle so file-on-disk invariant holds.
        await state.first_cycle_done.wait()
        return state

    # Pre-flight: how stale is the run on the remote?
    try:
        newest_remote = await _remote_newest_md_mtime(rel_path)
    except ssh_helper.RemoteError as e:
        state.last_error = str(e)
        state.last_cycle_ok = False
        state.cycle_failures = 1
        state.done = True
        state.done_reason = "preflight_failed"
        state.first_cycle_done.set()
        asyncio.create_task(_retire_task(rel_path, delay=30.0))
        return state

    stale_threshold = settings.sync_preflight_stale_hours * 3600
    is_stale = (
        newest_remote is None or (time.time() - newest_remote) > stale_threshold
    )
    # Seed idle clock with pre-flight mtime so partly-stalled runs don't get a
    # fresh 30-minute budget.
    if newest_remote is not None:
        state.last_mtime_seen = newest_remote

    if is_stale:
        # One-shot rsync, no loop.
        await _do_rsync(state)
        state.done = True
        state.done_reason = "one_shot"
        state.first_cycle_done.set()
        asyncio.create_task(_retire_task(rel_path, delay=30.0))
        return state

    # Fresh: spawn the loop task and wait for its first cycle to land.
    state.task = asyncio.create_task(_sync_loop(state))
    await state.first_cycle_done.wait()
    return state


def get_state(rel_path: str) -> SyncTaskState | None:
    """Return the current SyncTaskState for `rel_path`, or None if no task."""
    return _tasks.get(rel_path)


async def stop(rel_path: str) -> None:
    """Cancel an in-flight sync task (rare — mainly for tests / admin)."""
    async with _tasks_lock:
        state = _tasks.get(rel_path)
    if state is None or state.done:
        return
    if state.task is not None:
        state.task.cancel()
        try:
            await state.task
        except asyncio.CancelledError:
            pass


# ─── File-stability helper ─────────────────────────────────────────────────

async def stable_read_text(path: Path, *, attempts: int = 4, delay: float = 0.2) -> str:
    """Read text from `path` only after its size has been stable across two
    consecutive samples `delay` seconds apart. Belt-and-suspenders for the
    rare producer-side partial-write window — rsync's default atomic rename
    on the receiver already protects local consumers in normal cases.

    Raises FileNotFoundError if the file disappears for all attempts.
    """
    last_size = -1
    for _ in range(attempts):
        if not path.is_file():
            await asyncio.sleep(delay)
            continue
        try:
            cur = path.stat().st_size
        except OSError:
            await asyncio.sleep(delay)
            continue
        if cur > 0 and cur == last_size:
            return await asyncio.to_thread(path.read_text, encoding="utf-8")
        last_size = cur
        await asyncio.sleep(delay)
    # Final read attempt without further waiting.
    return await asyncio.to_thread(path.read_text, encoding="utf-8")

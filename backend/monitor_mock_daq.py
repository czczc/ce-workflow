"""In-app mock-DAQ launcher for /monitor.

Spawns `scripts/mock_daq.py --random` as a child process so the page can drip-
feed itself fake QC data without dropping to a terminal. One process at a
time, scoped to local-mode (no remote sync). See #70.
"""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import settings


_SCRIPT = Path(__file__).parent / "scripts" / "mock_daq.py"


class _State:
    process: Optional[asyncio.subprocess.Process] = None
    started_at: float = 0.0
    dest_name: str = ""
    rel_path: str = ""  # Time_YYYY_MM/<dest_name>


_state = _State()


def _is_running() -> bool:
    """True iff a child is alive; lazily reap on the way out."""
    p = _state.process
    if p is None:
        return False
    if p.returncode is not None:
        _state.process = None
        return False
    return True


def _compute_dest() -> tuple[str, str]:
    """Return (dest_name, rel_path) matching mock_daq.py's default naming so the
    caller can show the user where the run will land."""
    now = datetime.now()
    dest_name = f"{now.day:02d}_{now.hour:02d}_{now.minute:02d}_{now.second:02d}_MOCK_LN_QC"
    rel_path = f"Time_{now.year:04d}_{now.month:02d}/{dest_name}"
    return dest_name, rel_path


def status() -> dict:
    running = _is_running()
    return {
        "running": running,
        "started_at": _state.started_at if running else None,
        "dest_name": _state.dest_name if running else None,
        "rel_path": _state.rel_path if running else None,
    }


async def start() -> dict:
    """Launch mock_daq.py --random as a child. Raises RuntimeError if one is
    already running. Caller is responsible for refusing in remote mode."""
    if _is_running():
        raise RuntimeError("a mock DAQ is already running")

    dest_name, rel_path = _compute_dest()
    args = [
        sys.executable,
        str(_SCRIPT),
        "--random",
        "--dest",
        dest_name,
        "--qc-root",
        settings.qc_root,
    ]
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    _state.process = proc
    _state.started_at = time.time()
    _state.dest_name = dest_name
    _state.rel_path = rel_path
    return status()


async def stop() -> dict:
    """Terminate the child if alive. Idempotent."""
    if not _is_running():
        return status()
    proc = _state.process
    assert proc is not None
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
    _state.process = None
    return status()

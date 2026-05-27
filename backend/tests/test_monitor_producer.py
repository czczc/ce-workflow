import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio

import monitor_session
from monitor_session import _build_session_meta, _file_producer


class _NoopObserver:
    """Stand-in for watchdog's Observer that delivers no FS events. Forces the
    producer to rely solely on its periodic disk rescan (the #68 fix)."""

    def schedule(self, *a, **k):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def join(self, *a, **k):
        pass


def _make_run_dir(tmp_path: Path) -> tuple[str, Path]:
    rel_path = "2026/05/Time_01/run_LN_QC"
    abs_path = tmp_path / rel_path
    (abs_path / "FEMB_IO-1865_S0").mkdir(parents=True)
    return rel_path, abs_path


async def _drain_until(queue: asyncio.Queue, type_: str, timeout: float) -> dict:
    """Pull events until one of `type_` arrives or the deadline passes."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        try:
            evt = await asyncio.wait_for(queue.get(), timeout=deadline - loop.time())
        except asyncio.TimeoutError:
            break
        if evt.get("type") == type_:
            return evt
    raise AssertionError(f"no {type_!r} event within {timeout}s")


async def _run_case(tmp_path: Path) -> None:
    rel_path, abs_path = _make_run_dir(tmp_path)
    meta = _build_session_meta(rel_path, abs_path)
    assert meta is not None and meta.fembs

    out: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(_file_producer(meta, out))
    try:
        # Let the producer finish its startup scan and enter the loop.
        await asyncio.sleep(0.3)
        assert out.empty(), "no files exist yet, nothing should be emitted"

        # New test result appears on disk; only the periodic rescan can find it.
        (abs_path / "FEMB_IO-1865_S0" / "report_FEMB_0_t1_P_S0.md").write_text("ok")
        evt = await _drain_until(out, "test_pass", timeout=3.0)
        assert evt["femb_id"] == "S0"
        assert evt["test_id"] == "t1"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def test_producer_surfaces_post_startup_file_without_watchdog(tmp_path, monkeypatch):
    """A report file that lands AFTER startup must reach the consumer even when
    watchdog fires nothing — proving the periodic rescan backstop (#68)."""
    monkeypatch.setattr(monitor_session, "Observer", _NoopObserver)
    asyncio.run(_run_case(tmp_path))

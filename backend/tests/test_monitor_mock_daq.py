import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import config
import monitor_mock_daq


class _FakeProc:
    """Stand-in for asyncio.subprocess.Process. `returncode is None` means
    'still running'; set it to simulate natural exit."""

    def __init__(self):
        self.returncode = None
        self.terminate_calls = 0
        self.kill_calls = 0

    def terminate(self):
        self.terminate_calls += 1
        self.returncode = -15  # SIGTERM

    def kill(self):
        self.kill_calls += 1
        self.returncode = -9

    async def wait(self):
        return self.returncode


@pytest.fixture(autouse=True)
def _reset_state():
    monitor_mock_daq._state.process = None
    monitor_mock_daq._state.started_at = 0.0
    monitor_mock_daq._state.dest_name = ""
    monitor_mock_daq._state.rel_path = ""
    yield
    monitor_mock_daq._state.process = None


def test_status_idle_by_default():
    s = monitor_mock_daq.status()
    assert s == {"running": False, "started_at": None, "dest_name": None, "rel_path": None}


def test_start_then_status_then_stop():
    fake = _FakeProc()
    with patch(
        "monitor_mock_daq.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=fake),
    ):
        before = monitor_mock_daq.status()
        assert before["running"] is False

        started = asyncio.run(monitor_mock_daq.start())
        assert started["running"] is True
        assert started["dest_name"].endswith("_MOCK_LN_QC")
        assert started["rel_path"].startswith("Time_")
        assert started["rel_path"].endswith(started["dest_name"])

        # Status sees the live proc
        assert monitor_mock_daq.status()["running"] is True

        # stop() terminates and clears state
        stopped = asyncio.run(monitor_mock_daq.stop())
        assert stopped["running"] is False
        assert fake.terminate_calls == 1
        assert fake.kill_calls == 0
        assert monitor_mock_daq._state.process is None


def test_start_rejects_when_already_running():
    fake = _FakeProc()
    with patch(
        "monitor_mock_daq.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=fake),
    ):
        asyncio.run(monitor_mock_daq.start())
        with pytest.raises(RuntimeError, match="already running"):
            asyncio.run(monitor_mock_daq.start())


def test_status_reaps_finished_subprocess():
    """If the child exits on its own (mock_daq runs to completion), status()
    should notice and report not-running."""
    procs: list[_FakeProc] = []

    async def _spawn(*a, **k):
        procs.append(_FakeProc())
        return procs[-1]

    with patch("monitor_mock_daq.asyncio.create_subprocess_exec", new=_spawn):
        asyncio.run(monitor_mock_daq.start())
        assert monitor_mock_daq.status()["running"] is True

        procs[0].returncode = 0  # process finished naturally
        s = monitor_mock_daq.status()
        assert s["running"] is False
        assert monitor_mock_daq._state.process is None

        # And start() should accept a fresh run
        asyncio.run(monitor_mock_daq.start())
        assert monitor_mock_daq.status()["running"] is True
        assert len(procs) == 2


def test_stop_is_idempotent_when_not_running():
    s = asyncio.run(monitor_mock_daq.stop())
    assert s["running"] is False


def test_endpoint_refuses_start_in_remote_mode():
    """The /monitor/mock-daq/start endpoint must 400 when remote mode is
    active — mock-DAQ only makes sense against the local mirror."""
    from fastapi.testclient import TestClient
    from main import app

    before = config.settings.remote_host
    try:
        config.set_monitor_mode("remote")
        with TestClient(app) as c:
            r = c.post("/monitor/mock-daq/start")
            assert r.status_code == 400
            assert "local mode" in r.json()["detail"]
    finally:
        config.settings.remote_host = before

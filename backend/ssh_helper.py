"""Async ssh / rsync subprocess wrappers with ControlMaster multiplexing.

A single persistent ssh connection per host amortizes handshake cost across
listing, pre-flight mtime checks, and rsync cycles. The control socket lives
under /tmp and is auto-closed by ssh ControlPersist=10m after idle.

The helpers are deliberately thin: callers handle stdout parsing and decide
how to surface failures. `RemoteError` distinguishes "remote misbehaved"
(exit != 0, timeout) from generic Python errors so callers can fall back.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

# Backend ssh options. We *do not* override ControlMaster / ControlPath /
# ControlPersist here — let the user's ~/.ssh/config drive multiplexing so
# the backend shares the same persistent connection (and ProxyJump chain)
# the user already has set up. Keeping our own ControlPath would force a
# fresh handshake on every call and break ProxyJump setups where pubkey
# only works on the inner hop.
SSH_OPTS: list[str] = [
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=15",
]

# Pre-rendered for the `rsync -e` option.
SSH_CMD_FOR_RSYNC = "ssh " + " ".join(SSH_OPTS)


class RemoteError(RuntimeError):
    """Raised when an ssh/rsync invocation fails (nonzero exit or timeout).

    The exception's str() includes the first non-empty line of stderr so the
    UI's red chip tooltip is actually useful for diagnosing the failure.
    """

    def __init__(self, message: str, *, returncode: int | None = None, stderr: str = "") -> None:
        if stderr:
            first = next(
                (ln.strip() for ln in stderr.splitlines() if ln.strip()),
                "",
            )
            if first:
                message = f"{message} — {first}"
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


async def ssh_run(host: str, *remote_args: str, timeout: float = 30.0) -> str:
    """Run `ssh <host> <remote_args>` and return stdout (decoded).

    Raises RemoteError on nonzero exit or timeout. The remote command is passed
    as a single concatenated argv to ssh, which is the standard pattern.
    """
    proc = await asyncio.create_subprocess_exec(
        "ssh", *SSH_OPTS, host, *remote_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RemoteError(f"ssh {host}: timeout after {timeout}s")
    if proc.returncode != 0:
        raise RemoteError(
            f"ssh {host}: exit {proc.returncode}",
            returncode=proc.returncode,
            stderr=err.decode(errors="replace"),
        )
    return out.decode(errors="replace")


async def rsync_pull(
    host: str,
    remote_path: str,
    local_path: Path,
    *,
    md_only: bool = True,
    timeout: float = 600.0,
) -> None:
    """Rsync `host:remote_path/` into `local_path/`.

    With md_only=True (default), only `.md` files are transferred, preserving
    directory structure. The receiver writes via temp+atomic-rename so the local
    watcher never sees a half-written file. Raises RemoteError on failure.
    """
    local_path.mkdir(parents=True, exist_ok=True)
    args: list[str] = ["rsync", "-a", "-e", SSH_CMD_FOR_RSYNC]
    if md_only:
        args += ["--include=*/", "--include=*.md", "--exclude=*"]
    # Trailing slashes are important: copy *contents* of remote_path into local_path.
    args += [f"{host}:{remote_path.rstrip('/')}/", str(local_path).rstrip("/") + "/"]

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RemoteError(f"rsync {host}:{remote_path}: timeout after {timeout}s")
    if proc.returncode != 0:
        raise RemoteError(
            f"rsync {host}:{remote_path}: exit {proc.returncode}",
            returncode=proc.returncode,
            stderr=err.decode(errors="replace"),
        )


async def probe(host: str, timeout: float = 6.0) -> bool:
    """Return True iff `ssh host true` succeeds (also primes the ControlMaster)."""
    try:
        await ssh_run(host, "true", timeout=timeout)
        return True
    except RemoteError:
        return False

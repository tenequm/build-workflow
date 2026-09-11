"""Bounded subprocesses for a review that never trusts the tree it reads."""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

from operator_driver.storage import Park

TIMEOUT_CODE = 124

# A reviewer session inherits only these names. Everything else in the driver's
# environment - provider keys, GitHub tokens, cloud credentials - is dropped, so a
# prompt-injecting diff has nothing to exfiltrate even if it convinces its reader.
ENV_ALLOWLIST = (
    # The two GEMINI names are the metered API-key lane, used when the subscription
    # window is exhausted. Exposure parity, not an exception: a session that can be
    # talked into printenv can equally cat the subscription token file under HOME.
    "GEMINI_API_KEY",
    "GEMINI_HOME",
    "HOME",
    "LANG",
    "LC_ALL",
    "LOGNAME",
    # opencode reads its Zen credential from XDG_DATA_HOME, which every opencode family
    # redirects per session to scope capture - so this name is the only way a Zen lane
    # reaches its provider at all. OPENROUTER_API_KEY is the same lane with a paid
    # multi-provider key instead. Exposure parity, as above.
    "OPENCODE_API_KEY",
    "OPENROUTER_API_KEY",
    "PATH",
    # pi keeps providers, auth, skills and project trust under the first and its
    # transcripts under the second. Redirecting both per session is what gives a pi lane
    # an empty configuration and a session root holding only this run.
    "PI_CODING_AGENT_DIR",
    "PI_CODING_AGENT_SESSION_DIR",
    "SHELL",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "TERM",
    "TMPDIR",
    "TZ",
    "USER",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
)


def env_overlay(names: list[str], directory: Path) -> dict[str, str]:
    """Per-session values for the environment names a family asks to have redirected.

    A family that keeps global state under one of these gets its own copy per session:
    opencode writes every session it has ever run into one SQLite store under
    XDG_DATA_HOME, so without this one session can read another's transcripts, the
    operator's whole history is in scope, and capture has no narrow source to point
    pond at. Only allowlisted names are redirectable, which config.load enforces.
    """
    return {name: str(directory / "env" / name.lower()) for name in names}


def command(
    argv: list[str],
    cwd: Path,
    *,
    timeout: float = 120,
    env: dict[str, str] | None = None,
    isolate: bool = False,
) -> tuple[int, bytes, bytes]:
    """Own the process group so a child that outlives its wrapper is still reaped."""
    environment = session_env(env or {}) if isolate else {**os.environ, **(env or {})}
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _killpg(proc)
        out, err = proc.communicate()
        return TIMEOUT_CODE, out, err
    except BaseException:
        _killpg(proc)
        proc.communicate()
        raise
    _killpg(proc)
    return proc.returncode, out, err


def _killpg(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def session_env(extra: dict[str, str]) -> dict[str, str]:
    """The credential allowlist: an explicit keep-list, never a deny-list."""
    kept = {name: os.environ[name] for name in ENV_ALLOWLIST if name in os.environ}
    # Bytecode caches are the one thing an otherwise read-only command leaves behind in
    # the tree it read, and a dirty reviewed tree is indistinguishable from tampering.
    return {**kept, "PYTHONDONTWRITEBYTECODE": "1", **extra}


def removals() -> dict[str, str | None]:
    """`launch_once` merges onto os.environ, so isolation is expressed as removals."""
    kept: dict[str, str | None] = {name: None for name in os.environ if name not in ENV_ALLOWLIST}
    kept["PYTHONDONTWRITEBYTECODE"] = "1"
    return kept


def shell(
    script: str, cwd: Path, *, timeout: float = 900, isolate: bool = False
) -> tuple[int, bytes, bytes]:
    """Run a repository command string. Not a login shell: no profile side effects."""
    return command(["bash", "-c", script], cwd, timeout=timeout, isolate=isolate)


def git(root: Path, *args: str, timeout: float = 120) -> str:
    code, out, err = command(["git", *args], root, timeout=timeout)
    if code:
        raise Park(f"git {args[0]}: {err.decode(errors='replace')[-1000:]}")
    return out.decode(errors="replace").strip()


def git_bytes(root: Path, *args: str, timeout: float = 120) -> bytes:
    code, out, err = command(["git", *args], root, timeout=timeout)
    if code:
        raise Park(f"git {args[0]}: {err.decode(errors='replace')[-1000:]}")
    return out


def git_ok(root: Path, *args: str, timeout: float = 120) -> bool:
    return command(["git", *args], root, timeout=timeout)[0] == 0

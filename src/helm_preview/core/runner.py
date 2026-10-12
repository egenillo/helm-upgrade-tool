"""Subprocess wrapper with error handling."""

from __future__ import annotations

import subprocess
from typing import Any

from helm_preview.config import DEFAULT_TIMEOUT


class RunError(Exception):
    """Raised when a subprocess fails: non-zero exit, missing binary or timeout."""

    def __init__(self, cmd: list[str], returncode: int, stderr: str) -> None:
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"Command {cmd!r} failed (exit {returncode}): {stderr.strip()}"
        )


# Per-command limit used when run() is not given an explicit timeout.
# None means no limit. Set once per CLI invocation via set_default_timeout().
_timeout: float | None = DEFAULT_TIMEOUT
_USE_DEFAULT: Any = object()


def set_default_timeout(seconds: float | None) -> None:
    """Set the timeout (seconds) for every later run(); None disables it."""
    global _timeout
    _timeout = seconds


def run(
    cmd: list[str], timeout: float | None = _USE_DEFAULT, stdin: str | None = None
) -> str:
    """Run subprocess, capture stdout, raise on non-zero exit."""
    if timeout is _USE_DEFAULT:
        timeout = _timeout
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",  # not the platform default (cp1252 on Windows)
            errors="replace",
            timeout=timeout,
            input=stdin,
        )
    except FileNotFoundError:
        raise RunError(
            cmd, 127, f"'{cmd[0]}' was not found on PATH. Install it or add it to PATH."
        ) from None
    except subprocess.TimeoutExpired:
        raise RunError(
            cmd, -1, f"timed out after {timeout:g}s (raise the limit with --timeout)"
        ) from None
    except OSError as e:
        raise RunError(cmd, 126, f"could not execute '{cmd[0]}': {e}") from None
    if result.returncode != 0:
        raise RunError(cmd, result.returncode, result.stderr)
    return result.stdout

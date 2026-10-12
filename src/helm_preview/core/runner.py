"""Subprocess wrapper with error handling."""

from __future__ import annotations

import subprocess

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


def run(cmd: list[str], timeout: int = DEFAULT_TIMEOUT, stdin: str | None = None) -> str:
    """Run subprocess, capture stdout, raise on non-zero exit."""
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
        raise RunError(cmd, -1, f"timed out after {timeout}s") from None
    except OSError as e:
        raise RunError(cmd, 126, f"could not execute '{cmd[0]}': {e}") from None
    if result.returncode != 0:
        raise RunError(cmd, result.returncode, result.stderr)
    return result.stdout

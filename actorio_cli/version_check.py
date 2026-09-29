"""Check PyPI for newer actorio-cli releases.

Started in a background thread before a command runs and joined (bounded)
after it finishes, so a slow or offline PyPI never delays the actual work.
A notice goes to stderr, never stdout — ``--json`` output must stay
parseable. Disabled for ``actorio mcp`` (stdout carries MCP protocol frames
there) and via the ACTORIO_NO_VERSION_CHECK env var. Checks are throttled to
once per 24h with a timestamp file next to the CLI config.
"""

import os
import sys
import threading
import time
from pathlib import Path

import httpx
import typer

import actorio_cli.config as cfg_module

PYPI_URL = "https://pypi.org/pypi/actorio-cli/json"
NO_CHECK_ENV = "ACTORIO_NO_VERSION_CHECK"
CHECK_INTERVAL_SECONDS = 24 * 3600
_TIMEOUT_SECONDS = 2.0

# In-flight check state: (thread, installed_version, holder). Set by
# start_version_check, joined by finish_version_check.
_active: tuple[threading.Thread, str, dict[str, str | None]] | None = None


def installed_version() -> str | None:
    try:
        from importlib.metadata import version

        return version("actorio-cli")
    except Exception:
        return None


def latest_version() -> str | None:
    try:
        resp = httpx.get(PYPI_URL, timeout=_TIMEOUT_SECONDS, follow_redirects=True)
        resp.raise_for_status()
        return resp.json()["info"]["version"]
    except Exception:
        return None


def _version_parts(v: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in v.split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            break
    return tuple(parts)


def is_newer(latest: str, current: str) -> bool:
    try:
        return _version_parts(latest) > _version_parts(current)
    except Exception:
        return False


def cache_path() -> Path:
    # Next to the config file, so the tests' DEFAULT_PATH patch isolates it too.
    return Path(cfg_module.DEFAULT_PATH).parent / ".last_version_check"


def should_check() -> bool:
    if os.environ.get(NO_CHECK_ENV):
        return False
    try:
        path = cache_path()
        if path.exists() and time.time() - path.stat().st_mtime < CHECK_INTERVAL_SECONDS:
            return False
    except OSError:
        pass
    return True


def upgrade_hint(prefix: str = sys.prefix) -> str:
    if "pipx" in prefix:
        return "pipx upgrade actorio-cli"
    return "pip install -U actorio-cli"


def start_version_check(ctx_subcommand: str | None):
    """Kick off the background PyPI check.

    The state lands in ``_active`` for finish_version_check to join — Typer
    discards the callback's return value, so it can't be passed directly.
    Returns None when the check is skipped (mcp mode, env var, throttled,
    or no installed version).
    """
    global _active
    _active = None
    if ctx_subcommand == "mcp" or not should_check():
        return None
    current = installed_version()
    if current is None:
        return None
    holder: dict[str, str | None] = {}

    def run() -> None:
        holder["latest"] = latest_version()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    _active = thread, current, holder
    return _active


def finish_version_check(_value, **_: object) -> None:
    """Join the background check and print an upgrade notice to stderr if newer.

    ``_value`` is the command's return value and ``**_`` the callback's
    option params — Typer forwards both; neither is needed here.
    """
    global _active
    started = _active
    _active = None
    if started is None:
        return
    thread, current, holder = started
    thread.join(timeout=_TIMEOUT_SECONDS + 1)
    try:
        # Touch on every attempt (success or failure) so an offline machine
        # doesn't hammer PyPI on every command.
        cache_path().touch()
    except OSError:
        pass
    latest = holder.get("latest")
    if latest and is_newer(latest, current):
        typer.echo(
            f"A new version of actorio-cli is available: {latest} "
            f"(installed: {current}).\nRun `{upgrade_hint()}` to update.",
            err=True,
        )

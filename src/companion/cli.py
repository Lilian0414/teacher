import multiprocessing
import time
from multiprocessing.process import BaseProcess
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn

from companion.settings import get_settings

_READINESS_TIMEOUT_SECONDS = 10.0
_READINESS_POLL_INTERVAL_SECONDS = 0.1
_HEALTH_REQUEST_TIMEOUT_SECONDS = 0.5
_PROCESS_JOIN_TIMEOUT_SECONDS = 2.0


class LauncherError(RuntimeError):
    """Raised when the local Core process cannot be started safely."""


def core() -> None:
    """Run the Core API using the shared environment-backed settings."""
    settings = get_settings()
    uvicorn.run("companion.main:app", host=settings.host, port=settings.port)


def _wait_for_core(process: BaseProcess, health_url: str) -> None:
    deadline = time.monotonic() + _READINESS_TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        if process.exitcode is not None:
            raise LauncherError(
                f"Core exited before becoming ready (exit code {process.exitcode})"
            )

        try:
            with urlopen(health_url, timeout=_HEALTH_REQUEST_TIMEOUT_SECONDS) as response:
                if response.status == 200:
                    return
        except (OSError, TimeoutError, URLError):
            pass

        time.sleep(_READINESS_POLL_INTERVAL_SECONDS)

    if process.exitcode is not None:
        raise LauncherError(f"Core exited before becoming ready (exit code {process.exitcode})")
    raise LauncherError(
        f"Core did not become ready at {health_url} within {_READINESS_TIMEOUT_SECONDS:g} seconds"
    )


def _stop_process(process: BaseProcess) -> None:
    if process.exitcode is not None:
        process.join(timeout=_PROCESS_JOIN_TIMEOUT_SECONDS)
        return

    process.terminate()
    process.join(timeout=_PROCESS_JOIN_TIMEOUT_SECONDS)
    if process.is_alive():
        process.kill()
        process.join(timeout=_PROCESS_JOIN_TIMEOUT_SECONDS)


def local() -> None:
    """Run Core and UI together for a simple local development experience."""
    from terminal_ui.app import run

    settings = get_settings()
    process = multiprocessing.Process(target=core)
    process.start()
    try:
        _wait_for_core(process, f"{settings.core_url}/health")
        run()
    finally:
        _stop_process(process)

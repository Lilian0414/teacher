import multiprocessing
import time
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest

from companion import cli


class FakeProcess:
    def __init__(self, *, exitcode: int | None = None, stuck: bool = False) -> None:
        self.exitcode = exitcode
        self.stuck = stuck
        self.started = False
        self.terminated = False
        self.killed = False
        self.join_timeouts: list[float | None] = []

    def start(self) -> None:
        self.started = True

    def terminate(self) -> None:
        self.terminated = True

    def join(self, timeout: float | None = None) -> None:
        self.join_timeouts.append(timeout)

    def is_alive(self) -> bool:
        return self.stuck and not self.killed

    def kill(self) -> None:
        self.killed = True


def configure_local(
    monkeypatch: pytest.MonkeyPatch,
    process: FakeProcess,
    *,
    run: Callable[[], None],
) -> list[str]:
    events: list[str] = []
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: SimpleNamespace(core_url="http://test:4321", core_log_path="/tmp/core.log"),
    )

    def make_process(**kwargs: Any) -> FakeProcess:
        assert kwargs["target"] is cli._combined_core
        assert kwargs["args"] == ("/tmp/core.log",)
        return process

    monkeypatch.setattr(multiprocessing, "Process", make_process)

    def wait_for_core(received_process: Any, health_url: str) -> None:
        assert received_process is process
        events.append(health_url)

    monkeypatch.setattr(cli, "_wait_for_core", wait_for_core)
    monkeypatch.setattr("terminal_ui.app.run", run)
    return events


def test_local_waits_for_configured_core_before_running_ui(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = FakeProcess()
    events = configure_local(monkeypatch, process, run=lambda: events.append("ui"))

    cli.local()

    assert process.started
    assert events == ["http://test:4321/health", "ui"]
    assert process.terminated
    assert process.join_timeouts == [cli._PROCESS_JOIN_TIMEOUT_SECONDS]


def test_local_does_not_run_ui_when_core_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    process = FakeProcess(exitcode=7)
    ui_called = False
    wait_for_core = cli._wait_for_core

    def run() -> None:
        nonlocal ui_called
        ui_called = True

    configure_local(monkeypatch, process, run=run)
    monkeypatch.setattr(cli, "_wait_for_core", wait_for_core)

    with pytest.raises(cli.LauncherError, match="exit code 7"):
        cli.local()

    assert not ui_called
    assert process.join_timeouts == [cli._PROCESS_JOIN_TIMEOUT_SECONDS]


def test_local_does_not_run_ui_after_readiness_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    process = FakeProcess()
    ui_called = False

    def run() -> None:
        nonlocal ui_called
        ui_called = True

    configure_local(monkeypatch, process, run=run)

    def timeout(_process: Any, _health_url: str) -> None:
        raise cli.LauncherError("timed out")

    monkeypatch.setattr(cli, "_wait_for_core", timeout)

    with pytest.raises(cli.LauncherError, match="timed out"):
        cli.local()

    assert not ui_called
    assert process.terminated


def test_local_cleans_up_when_ui_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    process = FakeProcess()

    def run() -> None:
        raise ValueError("UI failed")

    configure_local(monkeypatch, process, run=run)

    with pytest.raises(ValueError, match="UI failed"):
        cli.local()

    assert process.terminated
    assert process.join_timeouts == [cli._PROCESS_JOIN_TIMEOUT_SECONDS]


def test_cleanup_kills_child_that_does_not_stop() -> None:
    process = FakeProcess(stuck=True)

    cli._stop_process(process)  # type: ignore[arg-type]

    assert process.terminated
    assert process.killed
    assert process.join_timeouts == [
        cli._PROCESS_JOIN_TIMEOUT_SECONDS,
        cli._PROCESS_JOIN_TIMEOUT_SECONDS,
    ]


def test_wait_for_core_polls_health_until_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    process = FakeProcess()
    requested: list[tuple[str, float]] = []
    responses = iter([OSError("not ready"), SimpleNamespace(status=200)])

    class ResponseContext:
        def __init__(self, response: Any) -> None:
            self.response = response

        def __enter__(self) -> Any:
            if isinstance(self.response, Exception):
                raise self.response
            return self.response

        def __exit__(self, *_args: object) -> None:
            return None

    def open_health(url: str, *, timeout: float) -> ResponseContext:
        requested.append((url, timeout))
        return ResponseContext(next(responses))

    monkeypatch.setattr(cli, "urlopen", open_health)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    cli._wait_for_core(process, "http://custom-host:9876/health")  # type: ignore[arg-type]

    assert requested == [
        ("http://custom-host:9876/health", cli._HEALTH_REQUEST_TIMEOUT_SECONDS),
        ("http://custom-host:9876/health", cli._HEALTH_REQUEST_TIMEOUT_SECONDS),
    ]

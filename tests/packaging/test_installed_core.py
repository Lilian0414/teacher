import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest


@pytest.mark.parametrize(
    "module",
    [
        "companion.main",
        "companion.api.dependencies",
        "companion.providers.schemas",
    ],
)
def test_installed_module_imports_in_fresh_process(module: str, tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": ""},
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr


def test_installed_core_serves_health_offline(tmp_path: Path) -> None:
    with socket.socket() as reserved_port:
        reserved_port.bind(("127.0.0.1", 0))
        port = reserved_port.getsockname()[1]

    environment = {
        **os.environ,
        "PYTHONPATH": "",
        "LLM_PROVIDER": "fake",
        "EMBEDDINGS_ENABLED": "false",
        "COMPANION_DATABASE_URL": f"sqlite:///{tmp_path / 'companion.sqlite3'}",
        "COMPANION_HOST": "127.0.0.1",
        "COMPANION_PORT": str(port),
    }
    command = Path(sys.executable).parent / "companion-core"
    process = subprocess.Popen(
        [str(command)],
        cwd=tmp_path,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 10
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                pytest.fail(f"companion-core exited early\nstdout:\n{stdout}\nstderr:\n{stderr}")
            try:
                with urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
                    assert json.load(response)["status"] == "ok"
                    break
            except URLError:
                time.sleep(0.1)
        else:
            pytest.fail("companion-core did not become healthy within 10 seconds")
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    assert process.returncode == 0

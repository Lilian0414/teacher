import os
import subprocess
import sys
from pathlib import Path


def test_installed_ui_imports_outside_repository(tmp_path: Path) -> None:
    environment = {**os.environ, "PYTHONPATH": ""}
    result = subprocess.run(
        [sys.executable, "-c", "import terminal_ui.app; print(terminal_ui.app.__file__)"],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "src/terminal_ui" in result.stdout or "site-packages/terminal_ui" in result.stdout

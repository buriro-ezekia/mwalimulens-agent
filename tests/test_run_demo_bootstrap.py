"""Tests for the judge-demo bootstrap command."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_demo.py"
SPEC = importlib.util.spec_from_file_location("mwalimulens_demo_bootstrap", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
demo_bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(demo_bootstrap)


def test_demo_command_uses_installed_package(tmp_path) -> None:
    python_path = tmp_path / "python"

    assert demo_bootstrap.build_demo_command(
        python_path,
        open_browser=True,
    ) == [
        str(python_path),
        "-m",
        "mwalimulens.demo_run",
        "--open",
    ]


def test_demo_command_can_disable_browser_open(tmp_path) -> None:
    python_path = tmp_path / "python"

    command = demo_bootstrap.build_demo_command(
        python_path,
        open_browser=False,
    )

    assert command[-1] == "--no-open"

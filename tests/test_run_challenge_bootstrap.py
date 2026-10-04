"""Tests for the standard-library clean-checkout bootstrap."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_challenge.py"
SPEC = importlib.util.spec_from_file_location("mwalimulens_bootstrap", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


def test_bootstrap_rejects_old_python() -> None:
    with pytest.raises(bootstrap.BootstrapError, match="Python 3.11"):
        bootstrap.ensure_python_supported((3, 10, 9))


def test_bootstrap_parses_node_version() -> None:
    assert bootstrap.parse_node_major("v24.16.0") == 24
    assert bootstrap.parse_node_major("20.10.0") == 20


def test_bootstrap_builds_installed_package_command(tmp_path) -> None:
    python_path = tmp_path / "python"
    command = bootstrap.build_challenge_command(
        python_path,
        model="qwen2.5:3b",
        base_url="http://127.0.0.1:11434/v1",
    )

    assert command == [
        str(python_path),
        "-m",
        "mwalimulens.challenge_run",
        "--model",
        "qwen2.5:3b",
        "--base-url",
        "http://127.0.0.1:11434/v1",
    ]


def test_venv_python_is_platform_specific(tmp_path) -> None:
    assert bootstrap.venv_python(tmp_path, windows=True) == (
        tmp_path / "Scripts" / "python.exe"
    )
    assert bootstrap.venv_python(tmp_path, windows=False) == (
        tmp_path / "bin" / "python"
    )

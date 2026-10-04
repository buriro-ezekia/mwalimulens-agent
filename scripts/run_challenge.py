"""Clean-checkout bootstrap for the complete MwalimuLens challenge run."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = PROJECT_ROOT / ".venv"
MIN_PYTHON = (3, 11)
MIN_NODE_MAJOR = 20
DEFAULT_MODEL = "qwen2.5:3b"


class BootstrapError(RuntimeError):
    """A prerequisite or installation step prevented the challenge run."""


def ensure_python_supported(version_info: Sequence[int] = sys.version_info) -> None:
    """Require the Python version declared by the project."""

    if tuple(version_info[:2]) < MIN_PYTHON:
        raise BootstrapError(
            "Python 3.11 or newer is required. "
            f"Found {version_info[0]}.{version_info[1]}."
        )


def venv_python(venv_dir: Path = VENV_DIR, *, windows: bool | None = None) -> Path:
    """Return the repository-local virtual-environment Python path."""

    windows = os.name == "nt" if windows is None else windows
    return (
        venv_dir / "Scripts" / "python.exe"
        if windows
        else venv_dir / "bin" / "python"
    )


def parse_node_major(value: str) -> int:
    """Parse output such as v24.16.0 into its major version."""

    match = re.fullmatch(r"v?(\d+)(?:\.\d+){1,2}", value.strip())
    if match is None:
        raise BootstrapError(f"Could not parse Node version: {value!r}")
    return int(match.group(1))


def ensure_node_supported(value: str) -> int:
    """Require the Node major version needed by the pinned npm dependency graph."""

    major = parse_node_major(value)
    if major < MIN_NODE_MAJOR:
        raise BootstrapError(
            f"Node {MIN_NODE_MAJOR}+ is required for the pinned MCP dependency. "
            f"Found {value.strip() or 'unknown'}."
        )
    return major


def require_command(name: str) -> str:
    """Resolve a required executable or raise a clear bootstrap error."""

    executable = shutil.which(name)
    if executable is None:
        raise BootstrapError(f"Required command is not available on PATH: {name}")
    return executable


def run_checked(
    command: Sequence[str],
    *,
    label: str,
    env: dict[str, str] | None = None,
) -> None:
    """Run one bootstrap step and fail at its original exit code."""

    print(f"==> {label}")
    try:
        completed = subprocess.run(
            list(command),
            cwd=PROJECT_ROOT,
            env=env,
            check=False,
        )
    except OSError as exc:
        raise BootstrapError(f"{label} could not start: {exc}") from exc
    if completed.returncode != 0:
        raise BootstrapError(
            f"{label} failed with exit code {completed.returncode}: "
            + " ".join(command)
        )


def bootstrap_environment() -> Path:
    """Create/install the local Python and Node environments reproducibly."""

    ensure_python_supported()

    python_path = venv_python()
    if not python_path.is_file():
        run_checked(
            [sys.executable, "-m", "venv", str(VENV_DIR)],
            label="Create repository virtual environment",
        )

    if not python_path.is_file():
        raise BootstrapError(f"Virtual-environment Python was not created: {python_path}")

    run_checked(
        [
            str(python_path),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-e",
            ".",
        ],
        label="Install MwalimuLens Python package",
    )

    node = require_command("node")
    npm = require_command("npm")
    node_version = subprocess.run(
        [node, "--version"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    ensure_node_supported(node_version)

    run_checked(
        [npm, "ci", "--no-audit", "--no-fund"],
        label="Install pinned borrowed-MCP npm dependencies",
    )
    return python_path


def build_challenge_command(
    python_path: Path,
    *,
    model: str,
    base_url: str | None,
) -> list[str]:
    """Build the installed-package challenge command."""

    command = [
        str(python_path),
        "-m",
        "mwalimulens.challenge_run",
        "--model",
        model,
    ]
    if base_url:
        command.extend(["--base-url", base_url])
    return command


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bootstrap and run the complete local MwalimuLens challenge workflow."
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Local Ollama model; default: {DEFAULT_MODEL}.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Optional Ollama OpenAI-compatible /v1 endpoint override.",
    )
    args = parser.parse_args()

    try:
        python_path = bootstrap_environment()
        env = dict(os.environ)
        env["PYDANTIC_AI_NO_BANNER"] = "1"
        run_checked(
            build_challenge_command(
                python_path,
                model=args.model,
                base_url=args.base_url,
            ),
            label="Run complete MwalimuLens challenge workflow",
            env=env,
        )
    except BootstrapError as exc:
        print(f"CHALLENGE BOOTSTRAP: FAIL\n{exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Bootstrap and launch the fast judge-facing MwalimuLens demo."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from run_challenge import BootstrapError, bootstrap_environment

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_demo_command(
    python_path: Path,
    *,
    open_browser: bool,
) -> list[str]:
    """Build the installed-package demo command."""

    command = [
        str(python_path),
        "-m",
        "mwalimulens.demo_run",
    ]
    command.append("--open" if open_browser else "--no-open")
    return command


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bootstrap and run the fast judge-facing MwalimuLens demo."
    )
    parser.add_argument(
        "--open",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Open the generated HTML in the default browser.",
    )
    args = parser.parse_args()

    try:
        python_path = bootstrap_environment()
        env = dict(os.environ)
        env["PYDANTIC_AI_NO_BANNER"] = "1"
        completed = subprocess.run(
            build_demo_command(
                python_path,
                open_browser=args.open,
            ),
            cwd=PROJECT_ROOT,
            env=env,
            check=False,
        )
    except BootstrapError as exc:
        print(f"DEMO BOOTSTRAP: FAIL\n{exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"DEMO BOOTSTRAP: FAIL\nCould not start demo: {exc}", file=sys.stderr)
        return 2

    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

"""One bounded Qwen attempt, provenance capture and read-only human-review verification."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR, PROJECT_ROOT
from mwalimulens.mcp_server.state import JsonStateStore
from mwalimulens.portal_qwen import BASE_URL, MODEL, QwenJob, saved_run_path

ARTIFACTS = (
    "portal_job.json", "report.json", "result.json", "proposals.json",
    "evidence_snapshot.json", "report.progress.json", "stdout.txt", "stderr.txt",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_new(path: Path, payload: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def preflight() -> dict[str, Any]:
    """Inspect source and installed model without generation, downloads or prewarming."""
    errors = []
    source: dict[str, Any] = {}
    provider: dict[str, Any] = {}
    try:
        def git(*args: str) -> str:
            return subprocess.run(
                ["git", *args], cwd=PROJECT_ROOT, capture_output=True,
                text=True, check=True, timeout=10,
            ).stdout.strip()

        source = {"head": git("rev-parse", "HEAD"),
                  "dirty": bool(git("status", "--porcelain")),
                  "fixture_sha256": {
                      path.name: _sha(path) for path in sorted(DEFAULT_DATA_DIR.glob("*.json"))
                  }}
        if source["dirty"]:
            errors.append("Use a clean, committed checkout before recording a genuine attempt.")
        if not source["fixture_sha256"]:
            errors.append("Fictional fixture files are unavailable.")
    except (OSError, subprocess.SubprocessError) as exc:
        errors.append(f"Source provenance unavailable: {type(exc).__name__}")
    try:
        with httpx.Client(base_url="http://127.0.0.1:11434", timeout=5, trust_env=False) as client:
            response = client.get("/api/version")
            response.raise_for_status()
            version = response.json()["version"]
            if not isinstance(version, str) or not version.strip():
                raise ValueError("Ollama version is missing")
            response = client.get("/api/tags")
            response.raise_for_status()
            models = response.json()["models"]
            if not isinstance(models, list) or any(not isinstance(item, dict) for item in models):
                raise ValueError("Ollama model metadata must be a list of objects")
            model = next((item for item in models
                          if item.get("name") == MODEL or item.get("model") == MODEL), None)
        if not model or not isinstance(model.get("digest"), str) or not model["digest"]:
            errors.append(
                f"Installed model {MODEL} with a digest was not found; nothing downloaded."
            )
        else:
            provider = {"version": version, "model": MODEL, "digest": model["digest"],
                        "base_url": BASE_URL}
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"Local Ollama metadata unavailable: {type(exc).__name__}")
    return {
        "ready": not errors, "checked_at": datetime.now(UTC).isoformat(),
        "source": source, "provider": provider, "errors": errors,
        "environment": {"os": platform.system(), "machine": platform.machine(),
                        "python": platform.python_version(), "logical_cpus": os.cpu_count()},
        "model_requests": 0,
    }


def run_once(output_root: Path, provenance: dict[str, Any]) -> dict[str, Any]:
    """Keep the existing one-request job and stop on every terminal outcome."""
    if provenance.get("ready") is not True:
        raise ValueError("Preflight is not ready; no model attempt was created")
    job = QwenJob(output_root)
    _write_new(job.run_dir / "session_provenance.json", {
        "artifact_version": "model_review_session_v1", "case_id": job.run_dir.name,
        "preflight": provenance, "request_limit": 1, "internal_deadline_seconds": 210,
        "worker_timeout_seconds": 240, "prewarm": False, "repair": False,
        "retrieval_actor": "application_controller", "model_tool_selection_evaluated": False,
        "teacher_identity": "simulated-teacher-not-authenticated",
    })
    try:
        job.start()
        while True:
            view = job.snapshot()
            if view["status"] != "running" and not view["worker_active"]:
                break
            time.sleep(0.25)
    finally:
        job.close()
    view = job.snapshot()
    receipt = {
        "artifact_version": "model_review_session_result_v1", "case_id": job.run_dir.name,
        "outcome": view["status"], "model_requests": view["request_count"],
        "error": view["error"], "recorded_at": datetime.now(UTC).isoformat(),
        "generation_sha256": {name: _sha(job.run_dir / name) for name in ARTIFACTS
                              if (job.run_dir / name).is_file()},
        "provenance_sha256": _sha(job.run_dir / "session_provenance.json"),
        "teacher_review_status": "pending" if view["status"] == "candidate" else "not_available",
        "sequence_complete": False, "semantic_quality_verified": False,
        "educator_moderation_verified": False,
    }
    _write_new(job.run_dir / "session_result.json", receipt)
    return {**receipt, "run_dir": str(job.run_dir)}


def verify_session(output_root: Path, case_id: str) -> dict[str, Any]:
    """Verify the same saved candidate after a teacher revision; never make a decision."""
    run_dir = saved_run_path(output_root, case_id)
    for name in ("session_provenance.json", "session_result.json"):
        path = run_dir / name
        if path.is_symlink() or path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Invalid session record")
    provenance_path = run_dir / "session_provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    receipt = json.loads((run_dir / "session_result.json").read_text(encoding="utf-8"))
    if not isinstance(provenance, dict) or not isinstance(receipt, dict):
        raise ValueError("Session records must be JSON objects")
    if (provenance.get("artifact_version") != "model_review_session_v1"
            or receipt.get("artifact_version") != "model_review_session_result_v1"
            or provenance.get("case_id") != case_id or receipt.get("case_id") != case_id
            or receipt.get("provenance_sha256") != _sha(provenance_path)):
        raise ValueError("Session identity or provenance has changed")
    hashes = receipt.get("generation_sha256")
    if (not isinstance(hashes, dict) or set(hashes) != set(ARTIFACTS)
            or any((run_dir / name).is_symlink() or _sha(run_dir / name) != hashes[name]
                   for name in ARTIFACTS)):
        raise ValueError("Generation records are missing or have changed")
    job = QwenJob.open_saved(output_root, case_id)
    view = job.snapshot()
    if (view["status"] != "candidate" or receipt.get("outcome") != "candidate"
            or receipt.get("model_requests") != 1 or view["request_count"] != 1):
        raise ValueError("This session has no verified single-request candidate to review")
    state = JsonStateStore(run_dir / "state.json")
    reviews, notes = state.teacher_reviews(), state.profile_updates()
    complete = (not state.pending_reviews() and len(reviews) == len(notes) == 1
                and reviews[0]["decision"] == "edit")
    return {
        "case_id": case_id, "outcome": view["status"], "model_requests": view["request_count"],
        "pending": len(state.pending_reviews()), "teacher_decisions": len(reviews),
        "synthetic_profile_notes": len(notes), "sequence_complete": complete,
        "teacher_reason": reviews[0]["reason"] if reviews else None,
        "final_wording": reviews[0]["final_claim"] if reviews else None,
        "reopening_verified": True, "semantic_quality_verified": False,
        "teacher_identity": "simulated-teacher-not-authenticated",
        "educator_moderation_verified": False,
        "note": "Local consistency checks, not authenticated teacher or signed provenance.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--run", action="store_true", help="Authorise one bounded local generation.")
    mode.add_argument("--verify", metavar="CASE_ID", help="Read-only post-revision verification.")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "runtime" / "portal")
    parser.add_argument("--no-open", action="store_true",
                        help="Save the result without opening UI.")
    args = parser.parse_args(argv)
    try:
        if args.verify:
            result = verify_session(args.output_dir, args.verify)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result["sequence_complete"] else 2
        provenance = preflight()
        if not args.run or not provenance["ready"]:
            print(json.dumps(provenance, indent=2, ensure_ascii=False))
            return 0 if provenance["ready"] else 2
        result = run_once(args.output_dir, provenance)
        print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
        if result["outcome"] != "candidate":
            return 2
        if not args.no_open:
            from mwalimulens.teacher_portal import main as portal_main

            return portal_main(["--output-dir", str(args.output_dir),
                                "--open-qwen", result["case_id"]])
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"error": str(exc), "sequence_complete": False}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

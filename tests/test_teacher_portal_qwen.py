"""Browser Qwen integration with mocked jobs and genuine synthetic review state."""

from __future__ import annotations

import http.client
import re
import subprocess
import threading
from copy import deepcopy
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode

import pytest

from mwalimulens import teacher_portal
from mwalimulens.domain import load_synthetic_dataset
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR
from mwalimulens.mcp_server.service import EducationToolService
from mwalimulens.mcp_server.state import JsonStateStore
from mwalimulens.teacher_portal import TeacherPortal, create_case, make_handler
from mwalimulens.teacher_review_demo import CANDIDATE

QWEN_CLAIM = "Recorded fraction-task scores differ; independent explanation needs checking."


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class FakeQwenJob:
    """A controllable completed/active job; never launches a model or process."""

    def __init__(self, root, index, complete_on_start=None):
        self.run_dir = root / f"qwen-fake-{index}"
        self.run_dir.mkdir()
        self.state_path = self.run_dir / "state.json"
        self.state = JsonStateStore(self.state_path)
        self.service = EducationToolService(load_synthetic_dataset(DEFAULT_DATA_DIR), self.state)
        self.start_calls = 0
        self.closed = False
        self.complete_on_start = complete_on_start
        self.view = {
            "status": "running", "stage": "retrieval", "report": None,
            "candidate": None, "evidence": [], "abstention_reason": None,
            "error": None, "request_count": 0,
        }

    def start(self):
        self.start_calls += 1
        assert self.start_calls == 1
        if self.complete_on_start == "abstained":
            self.abstain()

    def _retrieved(self):
        self.view["evidence"] = self.service.get_competency_evidence(
            "L001", "MATH-FRACTIONS",
        )["evidence"]

    def candidate(self, claim=QWEN_CLAIM):
        self._retrieved()
        proposed = {**CANDIDATE, "claim": claim}
        candidate = self.service.flag_pattern_for_review(**proposed)
        self.view.update({
            "status": "candidate", "stage": "complete", "candidate": candidate,
            "request_count": 1,
            "report": {"status": "pass", "proposal_status": "submitted",
                       "model": "qwen2.5:3b", "model_requests": [{"status": "returned"}],
                       "decision_schema_id": "review_decision_outcome_v2"},
        })

    def abstain(self, reason="Task comparability remains unresolved for this fictional case."):
        self._retrieved()
        self.view.update({
            "status": "abstained", "stage": "complete", "abstention_reason": reason,
            "request_count": 1,
            # The failed positive benchmark must not turn valid abstention into a UI error.
            "report": {"status": "fail", "proposal_status": "abstained",
                       "model": "qwen2.5:3b", "error": None, "termination": None,
                       "decision_schema_id": "review_decision_outcome_v2"},
        })

    def fail(self, *, partial_candidate=False):
        if partial_candidate:
            self.candidate()
        self.view.update({
            "status": "error", "stage": "complete", "candidate": None,
            "error": "Model request failed <script>untrusted()</script>",
            "report": {"status": "fail", "proposal_status": "interrupted",
                       "model": "qwen2.5:3b", "error": {"type": "RuntimeError"}},
        })

    def snapshot(self):
        return deepcopy(self.view)

    def close(self):
        self.closed = True


class JobFactory:
    def __init__(self):
        self.jobs = []
        self.complete_on_start = None

    def __call__(self, root):
        job = FakeQwenJob(root, len(self.jobs), self.complete_on_start)
        self.jobs.append(job)
        return job


def request(port, method="GET", path="/", fields=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=4)
    supplied = {"Host": f"127.0.0.1:{port}"}
    supplied.update(headers or {})
    body = None
    if fields is not None:
        body = urlencode(fields)
        supplied["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        connection.request(method, path, body=body, headers=supplied)
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8"), dict(response.getheaders())
    finally:
        connection.close()


@pytest.fixture
def harness(tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Browser contract tests must not start a real subprocess or model")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    active = []

    def build(*, enabled=True):
        root = tmp_path / f"portal-{len(active)}"
        factory = JobFactory()
        portal = TeacherPortal(
            root, create_case(root), qwen_enabled=enabled, qwen_job_factory=factory,
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(portal))
        thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True,
        )
        thread.start()
        active.append((portal, server, thread))
        return portal, server.server_port, factory

    yield build
    for portal, server, thread in active:
        server.shutdown()
        server.server_close()
        portal.close()
        thread.join(timeout=3)


def start(portal, port, *, run_nonce=None):
    return request(port, "POST", "/case/start", {
        "csrf": portal.token, "mode": "qwen",
        "run_nonce": portal.run_nonce if run_nonce is None else run_nonce,
    })


def counts(state):
    return tuple(len(method()) for method in (
        state.pending_reviews, state.teacher_reviews, state.profile_updates,
    ))


def file_bytes(root):
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


def confirmation_nonce(html):
    match = re.search(r'name="nonce" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def test_qwen_is_opt_in_and_get_queries_cannot_launch_it(harness):
    portal, port, factory = harness(enabled=False)
    before = file_bytes(portal.output_root)
    status, html, _ = request(port, path="/?mode=qwen&run_nonce=anything")
    assert status == 200
    assert not any(
        tag == "input" and attrs.get("name") == "mode" and attrs.get("value") == "qwen"
        for tag, attrs in Elements(html).elements
    )
    assert start(portal, port)[0] == 403
    assert factory.jobs == []
    assert file_bytes(portal.output_root) == before


def test_explicit_post_starts_one_isolated_job_and_get_polling_is_read_only(harness):
    portal, port, factory = harness()
    seeded_path = portal.case.run_dir
    status, _, _ = start(portal, port)
    assert status in {200, 202, 303}
    job = factory.jobs[0]
    assert portal.case.mode == "qwen"
    assert portal.case.run_dir != seeded_path
    assert counts(portal.case.state) == (0, 0, 0)
    before = file_bytes(portal.output_root)
    for path in ("/", "/?", "/?mode=qwen", "/?nonce=unused"):
        status, html, headers = request(port, path=path)
        assert status == 200
        assert headers["Cache-Control"] == "no-store"
        assert any(tag == "meta" and attrs.get("http-equiv", "").lower() == "refresh"
                   and "url=/" in attrs.get("content", "").lower()
                   for tag, attrs in Elements(html).elements)
        assert not any(tag == "form" and attrs.get("action") == "/review/preview"
                       for tag, attrs in Elements(html).elements)
    assert len(factory.jobs) == job.start_calls == 1
    assert file_bytes(portal.output_root) == before


@pytest.mark.parametrize("kind", [
    "missing_csrf", "bad_nonce", "missing_nonce", "origin", "unicode_csrf", "unicode_nonce",
])
def test_qwen_start_keeps_request_guards(harness, kind):
    portal, port, factory = harness()
    fields = {"csrf": portal.token, "mode": "qwen", "run_nonce": portal.run_nonce}
    headers = None
    if kind == "missing_csrf":
        fields.pop("csrf")
    elif kind == "bad_nonce":
        fields["run_nonce"] = "stale"
    elif kind == "missing_nonce":
        fields.pop("run_nonce")
    elif kind == "unicode_csrf":
        fields["csrf"] = "\N{SNOWMAN}"
    elif kind == "unicode_nonce":
        fields["run_nonce"] = "\N{SNOWMAN}"
    else:
        headers = {"Origin": "https://untrusted.example"}
    assert request(port, "POST", "/case/start", fields, headers)[0] in {403, 409}
    assert factory.jobs == []


@pytest.mark.parametrize("path,extra", [
    ("/case/start", {"mode": "seeded"}),
    ("/case/start", {"mode": "mcp"}),
    ("/case/start", {"mode": "qwen"}),
    ("/review/preview", {"decision": "approve", "reason": "An earlier case reason."}),
    ("/review/submit", {"nonce": "an-old-confirmation"}),
])
def test_active_job_blocks_case_changes_and_review_writes(harness, path, extra):
    portal, port, factory = harness()
    start(portal, port)
    before = file_bytes(portal.output_root)
    fields = {"csrf": portal.token, "run_nonce": portal.run_nonce, **extra}
    assert request(port, "POST", path, fields)[0] == 409
    assert len(factory.jobs) == 1
    assert file_bytes(portal.output_root) == before
    assert counts(portal.case.state) == (0, 0, 0)


def test_consumed_nonce_blocks_duplicate_start_after_instant_completion(harness):
    portal, port, factory = harness()
    factory.complete_on_start = "abstained"
    original = portal.run_nonce
    start(portal, port, run_nonce=original)
    request(port)
    assert start(portal, port, run_nonce=original)[0] == 409
    assert len(factory.jobs) == 1
    assert portal.run_nonce != original


@pytest.mark.parametrize("failure", ["constructor", "start"])
@pytest.mark.parametrize("previous", ["seeded", "qwen"])
def test_startup_failure_has_no_previous_candidate_controls(
    harness, monkeypatch, failure, previous,
):
    portal, port, factory = harness()
    if previous == "qwen":
        start(portal, port)
        factory.jobs[0].candidate()
        request(port)
    original_case = portal.case
    original_job = portal.qwen_job
    original_claim = original_case.candidate["claim"]
    jobs_before = len(factory.jobs)

    def fail(*_args, **_kwargs):
        raise OSError("Synthetic output failure")

    if failure == "constructor":
        portal.qwen_job_factory = fail
    else:
        monkeypatch.setattr(FakeQwenJob, "start", fail)
    status, html, _ = start(portal, port)
    assert status == 422
    assert original_claim not in html
    assert not any(tag == "form" and attrs.get("action") == "/review/preview"
                   for tag, attrs in Elements(html).elements)
    assert counts(original_case.state) == (1, 0, 0)
    if failure == "constructor":
        assert portal.case is original_case
        assert portal.qwen_job is original_job
        assert len(factory.jobs) == jobs_before
    else:
        assert portal.qwen_job is None
        assert portal.case.mode == "qwen" and portal.case.candidate is None
        assert factory.jobs[-1].closed is True
        assert counts(portal.case.state) == (0, 0, 0)


def test_valid_abstention_shows_its_reason_without_seeded_fallback_or_review_form(harness):
    portal, port, factory = harness()
    initial_claim = portal.case.candidate["claim"]
    start(portal, port)
    reason = 'Comparability is unresolved <script>alert("test")</script>.'
    factory.jobs[0].abstain(reason)
    status, html, _ = request(port)
    assert status == 200
    assert "Comparability is unresolved &lt;script&gt;" in html
    assert '<script>alert("test")</script>' not in html
    assert initial_claim not in html
    assert portal.case.candidate is None
    assert counts(portal.case.state) == (0, 0, 0)
    assert not any(tag == "form" and attrs.get("action") == "/review/preview"
                   for tag, attrs in Elements(html).elements)
    assert request(port, "POST", "/review/preview", {
        "csrf": portal.token, "decision": "approve", "reason": "There is no candidate.",
    })[0] == 409
    assert not any(tag == "meta" and attrs.get("http-equiv", "").lower() == "refresh"
                   for tag, attrs in Elements(html).elements)


def test_failed_start_cleanup_does_not_restore_approval_controls(harness, monkeypatch):
    portal, port, _factory = harness()

    def fail(*_args, **_kwargs):
        raise OSError("Synthetic lifecycle failure")

    monkeypatch.setattr(FakeQwenJob, "start", fail)
    monkeypatch.setattr(FakeQwenJob, "close", fail)
    assert start(portal, port)[0] == 422
    assert portal.case.mode == "qwen" and portal.case.candidate is None
    assert request(port, "POST", "/review/preview", {
        "csrf": portal.token, "decision": "approve", "reason": "No completed proposal.",
    })[0] == 409
    assert counts(portal.case.state) == (0, 0, 0)


@pytest.mark.parametrize("partial_candidate", [False, True])
def test_errors_never_expose_review_controls_or_reuse_seeded_candidate(harness, partial_candidate):
    portal, port, factory = harness()
    initial_claim = portal.case.candidate["claim"]
    start(portal, port)
    factory.jobs[0].fail(partial_candidate=partial_candidate)
    status, html, _ = request(port)
    assert status == 200
    assert initial_claim not in html
    assert "<script>untrusted()</script>" not in html
    assert portal.case.candidate is None
    assert not any(tag == "form" and attrs.get("action") == "/review/preview"
                   for tag, attrs in Elements(html).elements)
    assert request(port, "POST", "/review/preview", {
        "csrf": portal.token, "decision": "approve", "reason": "An incomplete run.",
    })[0] == 409
    assert len(portal.case.state.teacher_reviews()) == 0
    assert len(portal.case.state.profile_updates()) == 0


def test_error_with_active_worker_keeps_polling_and_blocks_another_run(harness):
    portal, port, factory = harness()
    start(portal, port)
    job = factory.jobs[0]
    job.fail()
    job.view["worker_active"] = True
    before = file_bytes(portal.output_root)

    status, html, _ = request(port)
    assert status == 200
    assert portal.case.analysis_status == "error" and portal.case.candidate is None
    assert any(tag == "meta" and attrs.get("http-equiv", "").lower() == "refresh"
               and "url=/" in attrs.get("content", "").lower()
               for tag, attrs in Elements(html).elements)
    assert not any(tag == "form" and attrs.get("action") == "/review/preview"
                   for tag, attrs in Elements(html).elements)
    for path, extra in (
        ("/case/start", {"mode": "seeded"}),
        ("/case/start", {"mode": "mcp"}),
        ("/case/start", {"mode": "qwen", "run_nonce": portal.run_nonce}),
        ("/review/preview", {"decision": "approve", "reason": "The worker is unfinished."}),
        ("/review/submit", {"nonce": "stale-confirmation"}),
    ):
        assert request(port, "POST", path, {"csrf": portal.token, **extra})[0] == 409
    assert len(factory.jobs) == 1
    assert counts(portal.case.state) == (0, 0, 0)
    assert file_bytes(portal.output_root) == before

    job.view["worker_active"] = False
    status, html, _ = request(port)
    assert status == 200
    assert not any(tag == "meta" and attrs.get("http-equiv", "").lower() == "refresh"
                   for tag, attrs in Elements(html).elements)
    assert len(factory.jobs) == 1  # Completion and refresh do not implicitly retry.
    assert start(portal, port)[0] == 202
    assert len(factory.jobs) == 2 and factory.jobs[1].start_calls == 1
    assert job.closed is True


@pytest.mark.parametrize("decision,notes", [("approve", 1), ("edit", 1), ("reject", 0)])
def test_qwen_candidate_uses_the_existing_confirmation_gate(harness, decision, notes):
    portal, port, factory = harness()
    start(portal, port)
    factory.jobs[0].candidate()
    status, html, _ = request(port)
    assert status == 200 and QWEN_CLAIM in html
    assert "Live MCP calls with a deterministic model; no Qwen inference" not in html
    assert counts(portal.case.state) == (1, 0, 0)
    status, html, _ = request(port, "POST", "/review/preview", {
        "csrf": portal.token, "decision": decision,
        "reason": "EV-008 leaves independent explanation uncertain.",
        "edited_claim": "Task-specific performance differs; explanation needs checking.",
    })
    assert status == 200 and "Not saved yet" in html
    confirmation = confirmation_nonce(html)
    assert counts(portal.case.state) == (1, 0, 0)
    request(port, path="/?")  # Returning without saving has no human consequence.
    assert counts(portal.case.state) == (1, 0, 0)
    status, html, _ = request(port, "POST", "/review/submit", {
        "csrf": portal.token, "nonce": confirmation,
    })
    assert status == 200 and "Review recorded" in html
    assert counts(portal.case.state) == (0, 1, notes)
    assert request(port, "POST", "/review/submit", {
        "csrf": portal.token, "nonce": confirmation,
    })[0] == 409
    assert counts(portal.case.state) == (0, 1, notes)


def test_qwen_start_invalidates_an_earlier_practice_confirmation(harness):
    portal, port, factory = harness()
    original_state = portal.case.state
    status, html, _ = request(port, "POST", "/review/preview", {
        "csrf": portal.token, "decision": "approve", "reason": "A practice decision.",
    })
    assert status == 200
    old_confirmation = confirmation_nonce(html)
    start(portal, port)
    factory.jobs[0].candidate()
    request(port)
    assert request(port, "POST", "/review/submit", {
        "csrf": portal.token, "nonce": old_confirmation,
    })[0] == 409
    assert counts(original_state) == (1, 0, 0)
    assert counts(portal.case.state) == (1, 0, 0)


def test_portal_close_stops_the_owned_job(harness):
    portal, port, factory = harness()
    start(portal, port)
    portal.close()
    portal.close()
    assert factory.jobs[0].closed is True


@pytest.mark.parametrize("enabled", [False, True])
def test_cli_enables_qwen_without_starting_inference(tmp_path, monkeypatch, enabled):
    captured = []

    def serve(portal, **_kwargs):
        captured.append(portal)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Enabling Qwen must not launch inference at startup")

    monkeypatch.setattr(teacher_portal, "serve", serve)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    args = ["--output-dir", str(tmp_path), "--no-open"]
    if enabled:
        args.append("--enable-qwen")
    assert teacher_portal.main(args) == 0
    assert captured[0].qwen_enabled is enabled
    assert captured[0].qwen_job is None
    assert captured[0].case.mode == "seeded"

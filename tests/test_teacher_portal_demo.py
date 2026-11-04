"""Authored examples use the real local confirmation flow, never Qwen or MCP clients."""

from __future__ import annotations

import http.client
import json
import re
import subprocess
import threading
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode

import pytest

from mwalimulens import portal_qwen, teacher_portal


def contents(root):
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


def counts(case):
    return tuple(len(method()) for method in (
        case.state.pending_reviews, case.state.teacher_reviews, case.state.profile_updates,
    ))


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


@pytest.fixture(autouse=True)
def no_inference(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Demonstration tests must not start inference or MCP subprocesses")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(portal_qwen.QwenJob, "__init__", forbidden)


@pytest.fixture
def harness(tmp_path):
    portal = teacher_portal.TeacherPortal(tmp_path, teacher_portal.create_case(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), teacher_portal.make_handler(portal))
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01})
    thread.start()
    try:
        yield portal, server.server_port
    finally:
        server.shutdown()
        server.server_close()
        portal.close()
        thread.join(timeout=3)


def post(portal, port, path, **fields):
    return request(port, "POST", path, {"csrf": portal.token, **fields})


def preview(portal, port, decision="approve"):
    status, html, _ = post(
        portal, port, "/review/preview", decision=decision,
        reason="For this authored case, EV-008 leaves independent explanation uncertain.",
        edited_claim="Recorded scores rose; independent explanation needs checking.",
    )
    assert status == 200 and "Not saved yet" in html
    assert "Authored example; not a Qwen result." in html
    assert portal.case.run_dir.name in html
    match = re.search(r'name="nonce" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


@pytest.mark.parametrize("path", ["/demos", "/demos?scenario=candidate", "/?demo=error"])
def test_navigation_is_read_only_and_keeps_sources_distinct(harness, path):
    portal, port = harness
    before = contents(portal.output_root)
    assert request(port, path=path)[0] == 200
    assert contents(portal.output_root) == before
    assert portal.case.mode == "seeded" and portal.qwen_job is None
    html = request(port, path="/demos")[1]
    assert "Authored examples, not Qwen results." in html
    assert "New candidate demonstration" in html and "New error demonstration" in html
    assert "Run local Qwen review" not in html


@pytest.mark.parametrize("decision,notes", [("approve", 1), ("edit", 1), ("reject", 0)])
def test_demonstration_confirmation_and_reopening_preserve_human_outcomes(harness, decision, notes):
    portal, port = harness
    original = portal.case.run_dir
    before_original = contents(original)
    status, html, _ = post(portal, port, "/demo/start", scenario="candidate")
    assert status == 200 and "Authored example; not a Qwen result." in html
    case_id = portal.case.run_dir.name
    assert portal.case.mode == "demo" and counts(portal.case) == (1, 0, 0)
    assert "0 / 0" in html and "Separate local-model validation" not in html
    before = contents(portal.output_root)
    nonce = preview(portal, port, decision)
    assert contents(portal.output_root) == before
    # Returning to evidence is a read-only cancellation of this preview.
    assert request(port)[0] == 200 and counts(portal.case) == (1, 0, 0)
    assert contents(portal.output_root) == before
    status, html, _ = post(portal, port, "/review/submit", nonce=nonce)
    assert status == 200 and counts(portal.case) == (0, 1, notes)
    assert "Authored example; not a Qwen result." in html
    if decision == "edit":
        assert "Recorded scores rose; independent explanation needs checking." in html
    assert post(portal, port, "/review/submit", nonce=nonce)[0] == 409
    assert counts(portal.case) == (0, 1, notes)
    before_reopen = contents(portal.output_root)
    for _ in range(2):
        status, html, _ = post(portal, port, "/demo/open", run_id=case_id)
        assert status == 200 and case_id in html
        assert "Saved demonstration reopened; no model request was made" in html
        assert 'action="/review/preview"' not in html
        assert counts(portal.case) == (0, 1, notes)
    assert contents(portal.output_root) == before_reopen
    assert contents(original) == before_original


def test_error_has_no_review_controls_and_cannot_record_a_decision(harness):
    portal, port = harness
    status, html, _ = post(portal, port, "/demo/start", scenario="error")
    assert status == 200 and "Demonstration error" in html
    assert "Simulated connection failure" in html and "not an observed Qwen failure" in html
    assert 'action="/review/preview"' not in html and counts(portal.case) == (0, 0, 0)
    before = contents(portal.output_root)
    assert post(portal, port, "/review/preview", decision="approve", reason="Test")[0] == 409
    assert post(portal, port, "/review/submit", nonce="unused")[0] == 409
    assert contents(portal.output_root) == before
    case_id = portal.case.run_dir.name
    assert post(portal, port, "/demo/open", run_id=case_id)[0] == 200
    assert contents(portal.output_root) == before and counts(portal.case) == (0, 0, 0)


@pytest.mark.parametrize("switch", ["new_candidate", "new_error", "reopen"])
def test_changing_demo_cases_invalidates_old_confirmation(harness, switch):
    portal, port = harness
    post(portal, port, "/demo/start", scenario="candidate")
    original = portal.case.run_dir
    before = contents(original)
    nonce = preview(portal, port)
    old_run_nonce = portal.run_nonce
    if switch == "reopen":
        post(portal, port, "/demo/open", run_id=original.name)
    else:
        post(portal, port, "/demo/start", scenario=switch.removeprefix("new_"))
    assert portal.run_nonce != old_run_nonce
    assert post(portal, port, "/review/submit", nonce=nonce)[0] == 409
    assert contents(original) == before


@pytest.mark.parametrize("path,fields", [
    ("/demo/start", {"scenario": "qwen"}),
    ("/demo/open", {"run_id": "../demo-outside"}),
    ("/demo/open", {"run_id": "qwen-existing"}),
    ("/case/open", {"run_id": "demo-existing"}),
])
def test_invalid_demo_actions_preserve_current_case(harness, path, fields):
    portal, port = harness
    original = portal.case
    before = contents(portal.output_root)
    assert post(portal, port, path, **fields)[0] == 422
    assert portal.case is original and contents(portal.output_root) == before


@pytest.mark.parametrize("path", ["/demo/start", "/demo/open"])
@pytest.mark.parametrize("guard", ["csrf", "origin", "busy"])
def test_demo_actions_keep_request_and_busy_worker_guards(harness, monkeypatch, path, guard):
    portal, port = harness
    fields = {"csrf": portal.token, "scenario": "candidate", "run_id": "demo-saved"}
    headers = {}
    if guard == "csrf":
        fields["csrf"] = "invalid"
    elif guard == "origin":
        headers["Origin"] = "https://untrusted.example"
    else:
        monkeypatch.setattr(portal, "_busy", lambda: True)
        assert 'disabled aria-disabled="true"' in request(port, path="/demos")[1]
    before = contents(portal.output_root)
    assert request(port, "POST", path, fields, headers)[0] == (409 if guard == "busy" else 403)
    assert contents(portal.output_root) == before


def test_rejected_demo_state_is_not_read_by_the_renderer(harness, monkeypatch):
    portal, port = harness
    post(portal, port, "/demo/start", scenario="candidate")
    path = portal.case.state.path
    state = json.loads(path.read_text())
    state["profile_updates"] = [{"claim": "Unapproved"}]
    path.write_text(json.dumps(state))

    def forbidden(*_args, **_kwargs):
        pytest.fail("Rejected saved state must not be read by rendering")

    monkeypatch.setattr(type(portal.case.state), "_load", forbidden)
    status, html, _ = post(portal, port, "/demo/open", run_id=portal.case.run_dir.name)
    assert status == 200 and "Saved demonstration could not be verified" in html
    assert "Not verified / Not verified" in html and 'action="/review/preview"' not in html
    assert portal.case.evidence == []
    assert request(port)[0] == 200


def test_demo_list_escapes_untrusted_metadata_and_never_lists_qwen_as_a_demo(harness):
    portal, port = harness
    post(portal, port, "/demo/start", scenario="error")
    manifest_path = portal.case.run_dir / "portal_demo.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["scenario"] = "<script>untrusted()</script>"
    manifest_path.write_text(json.dumps(manifest))
    qwen = portal.output_root / "qwen-actual"
    qwen.mkdir()
    (qwen / "portal_job.json").write_text('{"status":"abstained"}')
    before = contents(portal.output_root)
    html = request(port, path="/demos")[1]
    assert "&lt;script&gt;untrusted()&lt;/script&gt;" in html
    assert "<script>" not in html and qwen.name not in html
    saved = request(port, path="/saved")[1]
    assert qwen.name in saved and portal.case.run_dir.name not in saved
    assert contents(portal.output_root) == before


@pytest.mark.parametrize("scenario", ["candidate", "error"])
def test_cli_can_start_and_reopen_demos_without_creating_a_practice_case(tmp_path, monkeypatch,
                                                                      scenario):
    observed = []
    monkeypatch.setattr(teacher_portal, "serve", lambda portal, **kwargs: observed.append(portal))
    args = ["--output-dir", str(tmp_path), "--no-open"]
    assert teacher_portal.main([*args, "--demo", scenario]) == 0
    case = observed[-1].case
    assert case.mode == "demo" and case.analysis_status == scenario
    assert len(list(tmp_path.iterdir())) == 1
    before = contents(tmp_path)
    assert teacher_portal.main([*args, "--open-demo", case.run_dir.name]) == 0
    assert observed[-1].case.run_dir == case.run_dir and contents(tmp_path) == before
    assert not observed[-1].qwen_enabled


@pytest.mark.parametrize("options", [
    ["--demo", "candidate", "--initial-mode", "seeded"],
    ["--demo", "error", "--open-qwen", "qwen-existing"],
    ["--open-demo", "demo-existing", "--demo", "candidate"],
])
def test_cli_initial_cases_are_mutually_exclusive(tmp_path, options):
    with pytest.raises(SystemExit) as exc:
        teacher_portal.main(["--output-dir", str(tmp_path), *options])
    assert exc.value.code == 2 and list(tmp_path.iterdir()) == []

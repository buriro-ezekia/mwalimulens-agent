"""Read-only cancellation navigation and preserved HTTP review boundaries."""
from __future__ import annotations

import http.client
import re
import threading
from copy import deepcopy
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

from mwalimulens.teacher_portal import Case, TeacherPortal, make_handler


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = []
        self.forms = []
        self.active = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.active = [attrs.get("href"), ""]
        if tag == "form":
            self.forms.append(attrs)

    def handle_data(self, data):
        if self.active is not None:
            self.active[1] += data

    def handle_endtag(self, tag):
        if tag == "a" and self.active is not None:
            self.links.append(tuple(self.active))
            self.active = None


def build_navigation_portal(root):
    """Use fictional state; no model, MCP or production service is started."""
    candidate = {
        "review_id": "navigation-review", "status": "pending_teacher_review",
        "claim": "Recorded scores differ; independent explanation remains uncertain.",
        "supporting_evidence_ids": ["EV-004", "EV-011"],
        "counter_evidence_ids": ["EV-008"],
        "uncertainty": "Different tasks limit direct score comparisons.",
        "suggested_teacher_question": "Can the learner explain an unfamiliar task unaided?",
    }
    reviews, updates, calls = [], [], []
    state = SimpleNamespace(
        candidate=candidate, reviews=reviews, updates=updates, calls=calls,
        review_candidate=lambda ident: dict(candidate),
        pending_reviews=lambda: (candidate,) if not reviews else (),
        teacher_reviews=lambda: tuple(reviews),
        profile_updates=lambda: tuple(updates),
        tool_calls=lambda: tuple(calls),
    )

    def record_review(*, review_id, reviewer_id, decision, reason, edited_claim=None):
        assert review_id == candidate["review_id"]
        assert reviewer_id == "simulated-teacher-not-authenticated"
        if reviews:
            raise ValueError("Already reviewed")
        candidate["status"] = {
            "approve": "approved_by_teacher", "edit": "edited_by_teacher",
            "reject": "rejected_by_teacher",
        }[decision]
        claim = (edited_claim if decision == "edit" else
                 None if decision == "reject" else candidate["claim"])
        reviews.append({"decision": decision, "reason": reason, "final_claim": claim})
        if decision != "reject":
            updates.append({"claim": claim})
        calls.append({"tool_name": "record_teacher_review", "status": "success",
                      "timestamp": "2026-11-02T00:00:00Z"})

    service = SimpleNamespace(record_teacher_review=record_review)
    evidence = [
        {"evidence_id": "EV-004", "term_id": "2025-T2", "evidence_type": "assessment",
         "score": .78, "observation": None},
        {"evidence_id": "EV-008", "term_id": "2025-T3", "evidence_type": "observation",
         "score": None, "observation": "Independent explanation needs checking."},
        {"evidence_id": "EV-011", "term_id": "2026-T2", "evidence_type": "practical_task",
         "score": .81, "observation": "Explained equivalence in a practical task."},
    ]
    case = Case(state, service, candidate, evidence, root, "seeded")
    return TeacherPortal(root, case)


@pytest.fixture
def navigation_server(tmp_path):
    portal = build_navigation_portal(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(portal))
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01})
    thread.start()
    try:
        yield portal, server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def call(port, method="GET", path="/", fields=None, headers=None):
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


def saved_state(portal):
    state = portal.case.state
    return deepcopy((state.candidate, state.reviews, state.updates, state.calls))


def preview(portal, port, decision="approve"):
    return call(port, "POST", "/review/preview", {
        "csrf": portal.token, "decision": decision, "reason": "Reviewing before deciding.",
        "edited_claim": "Recorded scores differ; independent reasoning needs assessment.",
    }, {"Origin": f"http://127.0.0.1:{port}", "Sec-Fetch-Site": "same-origin"})


@pytest.mark.parametrize("path", ["/", "/?", "/?view=evidence", "/?decision=approve&nonce=x"])
def test_home_query_does_not_change_review_state(navigation_server, path):
    portal, port = navigation_server
    before = saved_state(portal)
    status, html, headers = call(port, path=path)
    assert status == 200
    assert "Learner Progress Review" in html
    assert headers["Cache-Control"] == "no-store"
    assert headers["Referrer-Policy"] == "same-origin"
    assert 'name="referrer" content="same-origin"' in html
    assert saved_state(portal) == before


@pytest.mark.parametrize("decision", ["approve", "edit", "reject"])
def test_return_from_each_preview_with_empty_query_is_read_only(navigation_server, decision):
    portal, port = navigation_server
    before = saved_state(portal)
    status, html, _ = preview(portal, port, decision)
    assert status == 200 and "Not saved yet" in html
    status, html, _ = call(port, path="/?")
    assert status == 200 and "Awaiting teacher review" in html
    assert saved_state(portal) == before
    assert len(portal.case.state.pending_reviews()) == 1


def test_go_back_uses_local_link_not_empty_get_form(navigation_server):
    portal, port = navigation_server
    status, html, _ = preview(portal, port)
    assert status == 200
    parsed = Links(html)
    assert ("/", "Go back without saving") in parsed.links
    assert all(form.get("method", "get").lower() != "get" for form in parsed.forms)
    assert any(form.get("action") == "/review/submit" for form in parsed.forms)


@pytest.mark.parametrize("path", ["/missing?", "/review/submit?", "/case/start?",
                                  "/favicon.ico/missing?", "/%2e%2e/README.md?"])
def test_unknown_get_routes_still_reject(navigation_server, path):
    portal, port = navigation_server
    before = saved_state(portal)
    assert call(port, path=path)[0] == 404
    assert saved_state(portal) == before


@pytest.mark.parametrize("path", ["/favicon.ico", "/favicon.ico?version=1"])
def test_favicon_query_is_read_only(navigation_server, path):
    portal, port = navigation_server
    before = saved_state(portal)
    assert call(port, path=path)[0] == 204
    assert saved_state(portal) == before


def test_host_guard_is_not_bypassed_by_empty_query(navigation_server):
    portal, port = navigation_server
    before = saved_state(portal)
    assert call(port, path="/?", headers={"Host": "evil.example"})[0] == 403
    assert saved_state(portal) == before


@pytest.mark.parametrize("path", ["/case/start?", "/review/preview?", "/review/submit?"])
def test_post_routes_remain_exact(navigation_server, path):
    portal, port = navigation_server
    before = saved_state(portal)
    assert call(port, "POST", path, {"csrf": portal.token})[0] == 404
    assert saved_state(portal) == before


@pytest.mark.parametrize("origin", ["null", "https://evil.example"])
def test_untrusted_origins_still_reject(navigation_server, origin):
    portal, port = navigation_server
    before = saved_state(portal)
    assert call(port, "POST", "/review/preview", {
        "csrf": portal.token, "decision": "approve", "reason": "Test",
    }, {"Origin": origin})[0] == 403
    assert saved_state(portal) == before


def test_missing_csrf_still_rejects(navigation_server):
    portal, port = navigation_server
    before = saved_state(portal)
    assert call(port, "POST", "/review/preview", {
        "decision": "approve", "reason": "Test",
    })[0] == 403
    assert saved_state(portal) == before


@pytest.mark.parametrize("decision,notes", [("approve", 1), ("edit", 1), ("reject", 0)])
def test_explicit_confirmation_remains_one_use(navigation_server, decision, notes):
    portal, port = navigation_server
    status, html, _ = preview(portal, port, decision)
    assert status == 200
    match = re.search(r'name="nonce" value="([^"]+)"', html)
    assert match is not None
    fields = {"csrf": portal.token, "nonce": match.group(1)}
    assert not portal.case.state.reviews
    assert call(port, "POST", "/review/submit", fields)[0] == 200
    assert len(portal.case.state.reviews) == 1
    assert len(portal.case.state.updates) == notes
    assert call(port, "POST", "/review/submit", fields)[0] == 409
    assert len(portal.case.state.reviews) == 1
    assert len(portal.case.state.updates) == notes

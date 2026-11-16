"""SSH preserves Host/Origin; only an explicitly configured loopback port is trusted."""

import http.client
import re
import threading
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode

import pytest

from mwalimulens import teacher_portal as portal_module


@pytest.fixture
def workspace(tmp_path, request):
    browser_port = getattr(request, "param", 8081)
    case = portal_module.demonstration_case(tmp_path, scenario="candidate")
    portal = portal_module.TeacherPortal(tmp_path, case, browser_port=browser_port)
    server = ThreadingHTTPServer(("127.0.0.1", 0), portal_module.make_handler(portal))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield portal, server
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def send(server, *, host="127.0.0.1:8081", path="/", fields=None, headers=()):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=4)
    body = urlencode(fields) if fields is not None else ""
    connection.putrequest("POST" if fields is not None else "GET", path, skip_host=True)
    connection.putheader("Host", host)
    if fields is not None:
        connection.putheader("Content-Type", "application/x-www-form-urlencoded")
        connection.putheader("Content-Length", str(len(body.encode("utf-8"))))
    for name, value in headers:
        connection.putheader(name, value)
    connection.endheaders(body.encode("utf-8"))
    response = connection.getresponse()
    result = response.status, response.read().decode("utf-8")
    connection.close()
    return result


def test_tunnel_port_supports_page_review_confirmation_and_saved_reopening(workspace):
    portal, server = workspace
    assert server.server_address[0] == "127.0.0.1"
    assert server.server_port != portal.browser_port
    status, page = send(server)
    assert status == 200
    assert "Authored demonstration" in page
    origin = (("Origin", "http://127.0.0.1:8081"), ("Sec-Fetch-Site", "same-origin"))
    reason = "Preserve uncertainty about independent explanation."
    wording = "Recorded scores differ across terms; assess independent explanation next."
    status, preview = send(
        server,
        path="/review/preview",
        fields={
            "csrf": portal.token,
            "decision": "edit",
            "reason": reason,
            "edited_claim": wording,
        },
        headers=origin,
    )
    assert status == 200
    assert portal.case.state.teacher_reviews() == portal.case.state.profile_updates() == ()
    nonce = re.search(r'name="nonce" value="([^"]+)"', preview)[1]
    status, _ = send(
        server,
        path="/review/submit",
        fields={
            "csrf": portal.token,
            "nonce": nonce,
        },
        headers=origin,
    )
    assert status == 200
    status, _ = send(
        server,
        path="/review/submit",
        fields={
            "csrf": portal.token,
            "nonce": nonce,
        },
        headers=origin,
    )
    assert status == 409
    case = portal_module.demonstration_case(portal.output_root, run_id=portal.case.run_dir.name)
    assert case.candidate["review_id"] == portal.case.candidate["review_id"]
    assert case.state.teacher_reviews()[0]["reason"] == reason
    assert case.state.teacher_reviews()[0]["final_claim"] == wording
    assert len(case.state.profile_updates()) == 1
    assert not case.state.pending_reviews()


@pytest.mark.parametrize("workspace", [None], indirect=True)
def test_tunnel_port_is_not_trusted_by_default(workspace):
    _, server = workspace
    assert send(server)[0] == 403
    assert send(server, host=f"127.0.0.1:{server.server_port}")[0] == 200


@pytest.mark.parametrize("host", ["evil.example:8081", "localhost:8081", "127.0.0.1:8082"])
def test_only_exact_configured_loopback_host_is_trusted(workspace, host):
    _, server = workspace
    assert send(server, host=host)[0] == 403
    assert send(server, host=host, headers=(("X-Forwarded-Host", "127.0.0.1:8081"),))[0] == 403


@pytest.mark.parametrize("origin", ["https://127.0.0.1:8081", "http://evil.example:8081", "null"])
def test_alias_origin_must_match_request_host(workspace, origin):
    portal, server = workspace
    fields = {"csrf": portal.token, "decision": "approve", "reason": "test"}
    assert (
        send(server, path="/review/preview", fields=fields, headers=(("Origin", origin),))[0] == 403
    )
    assert portal.case.state.teacher_reviews() == ()


def test_another_trusted_port_is_still_cross_origin(workspace):
    portal, server = workspace
    fields = {"csrf": portal.token, "decision": "approve", "reason": "test"}
    status, _ = send(
        server,
        path="/review/preview",
        fields=fields,
        headers=(("Origin", f"http://127.0.0.1:{server.server_port}"),),
    )
    assert status == 403


@pytest.mark.parametrize(
    "headers",
    [
        (("Host", "127.0.0.1:8081"),),
        (("Origin", "http://127.0.0.1:8081"), ("Origin", "http://127.0.0.1:8081")),
        (("Sec-Fetch-Site", "cross-site"),),
    ],
)
def test_duplicate_or_cross_site_headers_cannot_submit(workspace, headers):
    portal, server = workspace
    status, _ = send(
        server,
        path="/review/preview",
        fields={
            "csrf": portal.token,
            "decision": "approve",
            "reason": "test",
        },
        headers=headers,
    )
    assert status == 403
    assert portal.case.state.teacher_reviews() == portal.case.state.profile_updates() == ()


def test_alias_keeps_csrf_gate(workspace):
    portal, server = workspace
    assert (
        send(
            server,
            path="/review/preview",
            fields={
                "decision": "approve",
                "reason": "test",
            },
            headers=(("Origin", "http://127.0.0.1:8081"),),
        )[0]
        == 403
    )
    assert portal.case.state.teacher_reviews() == ()


@pytest.mark.parametrize("workspace", [80], indirect=True)
def test_http_default_browser_port_is_canonicalised(workspace):
    portal, server = workspace
    assert send(server, host="127.0.0.1")[0] == 200
    status, _ = send(
        server,
        host="127.0.0.1",
        path="/review/preview",
        fields={
            "csrf": portal.token,
            "decision": "approve",
            "reason": "test",
        },
        headers=(("Origin", "http://127.0.0.1"),),
    )
    assert status == 200
    assert portal.case.state.teacher_reviews() == ()


@pytest.mark.parametrize("port", [0, -1, 65536, True, "8081"])
def test_browser_port_option_is_bounded(port, tmp_path):
    with pytest.raises(ValueError, match="browser port"):
        portal_module.TeacherPortal(tmp_path, None, browser_port=port)


def test_cli_rejects_invalid_browser_port_before_creating_a_case(tmp_path):
    with pytest.raises(SystemExit) as exc:
        portal_module.main(["--browser-port", "0", "--output-dir", str(tmp_path / "cases")])
    assert exc.value.code == 2
    assert not (tmp_path / "cases").exists()

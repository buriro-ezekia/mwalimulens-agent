"""The recording view serves only fresh real output and fails closed on lost visibility."""

from __future__ import annotations

import http.client
import json
import os
import time
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from mwalimulens import demo_run
from mwalimulens.recording_browser import (
    NAVIGATION,
    RecordingBrowser,
    RecordingBrowserError,
    navigation_stage,
    notify_recording_ready,
    validate_recording_url,
)


@pytest.fixture
def browser(tmp_path):
    with RecordingBrowser(tmp_path) as browser:
        yield browser


def _html(browser: RecordingBrowser) -> Path:
    path = browser.runtime_dir / "mwalimulens_demo.html"
    path.write_text("<!doctype html><body>Real demo result</body>", encoding="utf-8")
    return path


def _request(browser, suffix="", *, payload=None, headers=None, url=None):
    parsed = urlsplit(url or browser.url)
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=2)
    request_headers = {"Origin": browser.origin}
    data = None
    if payload is not None:
        data = json.dumps(payload)
        request_headers["Content-Type"] = "application/json"
    request_headers.update(headers or {})
    connection.request(
        "POST" if payload is not None else "GET",
        parsed.path + suffix,
        data,
        request_headers,
    )
    response = connection.getresponse()
    result = response.status, response.read(), dict(response.getheaders())
    connection.close()
    return result


def _heartbeat(browser, *, section="hero", **kwargs):
    return _request(
        browser,
        "heartbeat",
        payload={"section": section, "visible": True, "focused": True, "in_view": True, **kwargs},
    )[0]


def test_only_published_fresh_artifact_is_served(browser, tmp_path):
    path = _html(browser)
    notify_recording_ready(browser.url, path)
    browser.wait_ready(0)
    assert browser.ready
    assert _request(browser)[0] == 425

    browser.publish(path)
    status, body, headers = _request(browser)
    assert status == 200
    assert b"Real demo result" in body
    assert b"getBoundingClientRect" in body
    assert b"EV-008" in body
    assert json.dumps(NAVIGATION).encode() in body
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Frame-Options"] == "DENY"
    assert "Access-Control-Allow-Origin" not in headers

    other = tmp_path / "secret.html"
    other.write_text("<body>not served</body>", encoding="utf-8")
    with pytest.raises(RecordingBrowserError, match="Only runtime"):
        browser.publish(other)
    assert _request(browser, "../secret.html")[0] == 404


def test_old_stage_and_stale_html_are_rejected(browser):
    path = _html(browser)
    browser.publish(path)
    old_url = browser.url
    os.utime(path, (1, 1))
    new_url = browser.begin_stage()
    assert new_url != old_url
    assert not browser.ready
    assert _request(browser, url=old_url)[0] == 404
    with pytest.raises(RecordingBrowserError, match="predates"):
        browser.publish(path)
    with pytest.raises(RecordingBrowserError, match="notify"):
        notify_recording_ready(new_url, path)
    assert not browser.ready
    with pytest.raises(RecordingBrowserError, match="did not load"):
        browser.wait_loaded(0)


def test_unchanged_preflight_html_is_rejected_even_with_recent_timestamp(browser):
    path = _html(browser)
    browser.publish(path)
    browser.begin_stage()
    with pytest.raises(RecordingBrowserError, match="predates"):
        browser.publish(path)


def test_foreign_host_origin_and_unknown_token_are_rejected(browser):
    browser.publish(_html(browser))
    assert _request(browser, headers={"Host": "attacker.invalid"})[0] == 403
    assert _request(browser, headers={"Origin": "https://attacker.invalid"})[0] == 403
    assert _request(browser, headers={"Sec-Fetch-Site": "cross-site"})[0] == 403
    assert _request(browser, url=browser.origin + "/wrong/")[0] == 404
    assert _request(browser, "?file=secret")[0] == 404
    assert _request(browser, "heartbeat", payload={}, headers={"Origin": ""})[0] == 403


def test_state_uses_shared_clock_and_is_unavailable_before_publication(browser):
    assert _request(browser, "state")[0] == 404
    browser.publish(_html(browser))
    browser.set_clock(time.monotonic() - 60)
    status, body, _ = _request(browser, "state")
    assert status == 200
    assert 60 <= json.loads(body)["elapsed"] < 62
    with pytest.raises(RecordingBrowserError, match="clock"):
        browser.set_clock(float("nan"))


def test_heartbeat_proves_loaded_visible_focused_scheduled_page(browser):
    browser.publish(_html(browser))
    browser.set_clock(time.monotonic() - 60)
    assert _heartbeat(browser, section="activity") == 200
    browser.wait_loaded(0)
    browser.check_health()

    assert _heartbeat(browser, section="candidate") == 200
    with pytest.raises(RecordingBrowserError, match="scheduled"):
        browser.check_health()
    assert _heartbeat(browser, section="activity", focused=False) == 200
    with pytest.raises(RecordingBrowserError, match="focused"):
        browser.check_health()
    browser.check_health(require_active=False)
    assert _heartbeat(browser, section="activity", visible=False) == 200
    with pytest.raises(RecordingBrowserError, match="hidden"):
        browser.check_health()
    assert _heartbeat(browser, section="activity", in_view=False) == 200
    with pytest.raises(RecordingBrowserError, match="scheduled"):
        browser.check_health()
    assert _heartbeat(browser, section="activity") == 200
    with pytest.raises(RecordingBrowserError, match="stale"):
        browser.check_health(max_age=0)


def test_page_request_alone_does_not_count_as_loaded(browser):
    browser.publish(_html(browser))
    assert _request(browser)[0] == 200
    with pytest.raises(RecordingBrowserError, match="did not load"):
        browser.wait_loaded(0)
    with pytest.raises(RecordingBrowserError, match="missing"):
        browser.check_health()
    assert _heartbeat(browser, visible="yes") == 400
    assert _heartbeat(browser, section="unknown") == 400


def test_open_checks_publication_and_browser_launch_result(browser, monkeypatch):
    with pytest.raises(RecordingBrowserError, match="published"):
        browser.open()
    browser.publish(_html(browser))
    opened = []
    monkeypatch.setattr("mwalimulens.recording_browser.webbrowser.open", opened.append)
    with pytest.raises(RecordingBrowserError, match="could not open"):
        browser.open()
    assert opened == [browser.url]
    monkeypatch.setattr("mwalimulens.recording_browser.webbrowser.open", lambda url: True)
    browser.open()


@pytest.mark.parametrize(
    ("seconds", "section"),
    [(0, "hero"), (31, "evidence"), (43, "counter-evidence"), (58, "activity"),
     (83, "candidate"), (103, "gate"), (119, "validation"), (141, "limitation")],
)
def test_navigation_timing(seconds, section):
    assert navigation_stage(seconds) == section


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:8080/" + "a" * 64 + "/" + "b" * 32 + "/",
        "http://example.com:8080/" + "a" * 64 + "/" + "b" * 32 + "/",
        "http://localhost:8080/" + "a" * 64 + "/" + "b" * 32 + "/",
        "http://user:pass@127.0.0.1:8080/" + "a" * 64 + "/" + "b" * 32 + "/",
        "http://127.0.0.1:8080/no-token/",
        "http://127.0.0.1:999999/",
        "file:///tmp/demo.html",
    ],
)
def test_hook_never_contacts_a_remote_or_ambiguous_url(url):
    with pytest.raises(RecordingBrowserError, match="tokenised"):
        validate_recording_url(url)


def _stub_demo(monkeypatch, tmp_path, *, status="pass"):
    monkeypatch.setattr("sys.argv", ["demo_run", "--html", str(tmp_path / "mwalimulens_demo.html")])
    monkeypatch.delenv("MWALIMULENS_RECORDING_URL", raising=False)

    async def fake_run(**kwargs):
        kwargs["html_path"].write_text("<body>Fresh result</body>", encoding="utf-8")
        return {"status": status}

    monkeypatch.setattr(demo_run, "run_demo", fake_run)
    monkeypatch.setattr(demo_run, "print_demo_summary", lambda *args: None)


def test_exact_cli_notifies_coordinator_without_opening_early(browser, monkeypatch):
    _stub_demo(monkeypatch, browser.runtime_dir)
    monkeypatch.setenv("MWALIMULENS_RECORDING_URL", browser.url)
    monkeypatch.setattr(demo_run.webbrowser, "open", lambda *args: pytest.fail("Opened too early"))
    assert demo_run.main() == 0
    assert browser.ready
    assert _request(browser)[0] == 425


def test_failed_demo_never_announces_ready(browser, monkeypatch):
    _stub_demo(monkeypatch, browser.runtime_dir, status="fail")
    monkeypatch.setenv("MWALIMULENS_RECORDING_URL", browser.url)
    assert demo_run.main() == 2
    assert not browser.ready


def test_normal_cli_opens_real_file_and_reports_browser_failure(tmp_path, monkeypatch, capsys):
    _stub_demo(monkeypatch, tmp_path)
    opened = []
    monkeypatch.setattr(demo_run.webbrowser, "open", lambda url: opened.append(url) or False)
    assert demo_run.main() == 2
    assert opened == [(tmp_path / "mwalimulens_demo.html").as_uri()]
    assert "browser could not open" in capsys.readouterr().err


def test_cli_rejects_bad_recording_url_before_running(tmp_path, monkeypatch, capsys):
    _stub_demo(monkeypatch, tmp_path)
    monkeypatch.setenv("MWALIMULENS_RECORDING_URL", "http://attacker.invalid/")
    assert demo_run.main() == 2
    assert not (tmp_path / "mwalimulens_demo.html").exists()
    assert "tokenised" in capsys.readouterr().err

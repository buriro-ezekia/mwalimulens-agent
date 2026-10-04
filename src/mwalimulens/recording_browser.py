"""Loopback-only navigation of the fresh, real demo page during recording.

This server never fabricates a demo result. The coordinator must validate and publish
the HTML produced by the live demo before a browser can load it.
"""

from __future__ import annotations

import json
import math
import re
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

RECORDING_URL_ENV = "MWALIMULENS_RECORDING_URL"
NAVIGATION = (
    (0, "hero"),
    (31, "evidence"),
    (43, "counter-evidence"),
    (58, "activity"),
    (83, "candidate"),
    (103, "gate"),
    (119, "validation"),
    (141, "limitation"),
)
_TOKEN_PATH = re.compile(r"/[0-9a-f]{64}/[0-9a-f]{32}/")


class RecordingBrowserError(RuntimeError):
    """A fresh, visible live browser view could not be verified."""


def navigation_stage(elapsed: float) -> str:
    """Return the section due at the coordinator's shared capture time."""

    return next(name for second, name in reversed(NAVIGATION) if elapsed >= second)


def validate_recording_url(url: str) -> str:
    """Accept only the coordinator's explicit IPv4 loopback URL shape."""

    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme == "http"
            and parsed.hostname == "127.0.0.1"
            and parsed.port is not None
            and 0 < parsed.port <= 65535
            and parsed.netloc == f"127.0.0.1:{parsed.port}"
            and _TOKEN_PATH.fullmatch(parsed.path)
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        valid = False
    if not valid:
        raise RecordingBrowserError(
            "Recording browser URL must be a tokenised http://127.0.0.1:<port>/ URL."
        )
    return url


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def notify_recording_ready(url: str, html_path: Path) -> None:
    """Tell the local coordinator a genuine demo has completed, without opening a tab."""

    url = validate_recording_url(url)
    parsed = urlsplit(url)
    request = Request(
        url + "ready",
        data=json.dumps({"html_path": str(html_path.resolve())}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Origin": f"http://{parsed.netloc}",
        },
        method="POST",
    )
    try:
        # Never send the token through an environment proxy or follow a redirect.
        with build_opener(ProxyHandler({}), _NoRedirect()).open(request, timeout=3) as response:
            if response.status != 200 or response.read(1024) != b'{"ready":true}':
                raise RecordingBrowserError("Recording coordinator rejected demo readiness.")
    except (OSError, URLError) as exc:
        raise RecordingBrowserError(
            "Could not notify the local recording coordinator; this take is invalid."
        ) from exc


class RecordingBrowser:
    """Serve one newly generated runtime HTML file and observe its live navigation."""

    def __init__(self, runtime_dir: Path) -> None:
        self.runtime_dir = runtime_dir.resolve()
        self._lock = threading.RLock()
        self._token = secrets.token_hex(32)
        self._stage = ""
        self._html: str | None = None
        self._ready = False
        self._clock: float | None = None
        self._started_ns = 0
        self._previous_file: tuple[int, int, int, int] | None = None
        self._heartbeat: dict[str, Any] | None = None
        self._closed = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                owner._handle(self, "GET")

            def do_POST(self) -> None:
                owner._handle(self, "POST")

            def log_message(self, format: str, *args: Any) -> None:
                # URLs contain a local bearer token. Do not write access logs.
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.begin_stage()

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}"

    @property
    def url(self) -> str:
        with self._lock:
            return self.origin + self._base_path

    @property
    def _base_path(self) -> str:
        return f"/{self._token}/{self._stage}/"

    @property
    def ready(self) -> bool:
        with self._lock:
            return self._ready

    def begin_stage(self) -> str:
        """Invalidate the rehearsal page before the independent live take begins."""

        with self._lock:
            self._stage = secrets.token_hex(16)
            self._started_ns = time.time_ns()
            try:
                self._previous_file = self._fingerprint(
                    self.runtime_dir / "mwalimulens_demo.html"
                )
            except FileNotFoundError:
                self._previous_file = None
            self._html = None
            self._ready = False
            self._clock = None
            self._heartbeat = None
            return self.url

    def set_clock(self, start: float) -> None:
        """Use the same monotonic capture origin as narration and recording."""

        if not math.isfinite(start) or start > time.monotonic() + 1:
            raise RecordingBrowserError("Invalid recording clock origin.")
        with self._lock:
            self._clock = start

    def _fresh_html(self, path: Path) -> str:
        expected = self.runtime_dir / "mwalimulens_demo.html"
        resolved = path.resolve()
        if resolved != expected or resolved.parent != self.runtime_dir:
            raise RecordingBrowserError("Only runtime/mwalimulens_demo.html may be served.")
        try:
            fingerprint = self._fingerprint(resolved)
            # Windows filesystem time may trail the high resolution system clock.
            # The saved fingerprint still rejects unchanged preflight output, even
            # within this small timestamp-resolution allowance.
            if (
                fingerprint[0] < self._started_ns - 1_000_000_000
                or fingerprint == self._previous_file
            ):
                raise RecordingBrowserError("Demo HTML predates this recording stage.")
            html = resolved.read_text(encoding="utf-8")
        except OSError as exc:
            raise RecordingBrowserError("Fresh demo HTML is missing or unreadable.") from exc
        if "</body>" not in html:
            raise RecordingBrowserError("The demo did not produce a complete HTML page.")
        return html

    @staticmethod
    def _fingerprint(path: Path) -> tuple[int, int, int, int]:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino

    def publish(self, html_path: Path) -> None:
        """Expose the fresh HTML only after the coordinator has validated the real run."""

        with self._lock:
            html = self._fresh_html(html_path)
            self._html = html.replace("</body>", self._script() + "</body>", 1)

    def wait_ready(self, timeout: float) -> None:
        self._wait(lambda: self.ready, timeout, "The live demo did not notify readiness.")

    def open(self) -> None:
        """Launch the published page; a failed launch cannot produce a valid take."""

        with self._lock:
            if self._html is None:
                raise RecordingBrowserError("Fresh live demo has not been published.")
        try:
            opened = webbrowser.open(self.url)
        except (OSError, webbrowser.Error) as exc:
            raise RecordingBrowserError("The live demo browser could not open.") from exc
        if not opened:
            raise RecordingBrowserError("The live demo browser could not open.")

    def wait_loaded(self, timeout: float) -> None:
        self._wait(
            lambda: self._heartbeat is not None,
            timeout,
            "The browser did not load the fresh demo page; this take is invalid.",
        )

    @staticmethod
    def _wait(predicate, timeout: float, message: str) -> None:
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() >= deadline:
                raise RecordingBrowserError(message)
            time.sleep(0.05)

    def check_health(self, max_age: float = 4, require_active: bool = True) -> None:
        """Reject a missing, hidden, stale or incorrectly navigated browser view."""

        with self._lock:
            heartbeat = self._heartbeat
            if heartbeat is None or time.monotonic() - heartbeat["received"] > max_age:
                raise RecordingBrowserError("Browser heartbeat is missing or stale.")
            if require_active and not (heartbeat["visible"] and heartbeat["focused"]):
                raise RecordingBrowserError("The live demo browser is hidden or not focused.")
            elapsed = self._elapsed()
            if self._clock is not None and require_active:
                # Allow one heartbeat interval at an exact section boundary.
                expected = navigation_stage(max(0, elapsed - 0.75))
                current = navigation_stage(elapsed)
                if heartbeat["section"] not in {expected, current} or not heartbeat["in_view"]:
                    raise RecordingBrowserError("The live browser missed its scheduled section.")

    def _elapsed(self) -> float:
        return max(0, time.monotonic() - self._clock) if self._clock is not None else 0

    def _handle(self, request: BaseHTTPRequestHandler, method: str) -> None:
        request.connection.settimeout(2)
        # Host and Origin checks prevent DNS rebinding and cross-origin local writes.
        if (
            request.client_address[0] != "127.0.0.1"
            or request.headers.get("Host") != urlsplit(self.origin).netloc
            or request.headers.get("Origin") not in (None, self.origin)
            or request.headers.get("Sec-Fetch-Site") == "cross-site"
            or (method == "POST" and request.headers.get("Origin") != self.origin)
        ):
            self._respond(request, 403, b"Forbidden")
            return
        with self._lock:
            prefix = self._base_path
            if not request.path.startswith(prefix):
                self._respond(request, 404, b"Not found")
                return
            endpoint = request.path[len(prefix):]
            if method == "GET" and endpoint == "":
                if self._html is None:
                    self._respond(request, 425, b"Fresh live demo has not been published.")
                else:
                    self._respond(request, 200, self._html.encode("utf-8"), "text/html")
            elif method == "GET" and endpoint == "state" and self._html is not None:
                body = json.dumps({"elapsed": self._elapsed()}).encode("utf-8")
                self._respond(request, 200, body, "application/json")
            elif method == "POST" and endpoint in {"ready", "heartbeat"}:
                self._post(request, endpoint)
            else:
                self._respond(request, 404, b"Not found")

    def _post(self, request: BaseHTTPRequestHandler, endpoint: str) -> None:
        try:
            length = int(request.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError("Invalid request size")
            if request.headers.get("Content-Type") != "application/json":
                raise ValueError("JSON required")
            payload = json.loads(request.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Object required")
            if endpoint == "ready":
                self._fresh_html(Path(payload["html_path"]))
                self._ready = True
                self._respond(request, 200, b'{"ready":true}', "application/json")
                return
            if self._html is None:
                raise ValueError("No page published")
            if (
                payload.get("section") not in {name for _, name in NAVIGATION}
                or any(
                    type(payload.get(key)) is not bool
                    for key in ("visible", "focused", "in_view")
                )
            ):
                raise ValueError("Invalid browser heartbeat")
            self._heartbeat = {**payload, "received": time.monotonic()}
            self._respond(request, 200, b"{}", "application/json")
        except (ValueError, KeyError, TypeError, OSError, RecordingBrowserError):
            self._respond(request, 400, b"Invalid or stale recording request")

    @staticmethod
    def _respond(request, status: int, body: bytes, content_type: str = "text/plain") -> None:
        request.send_response(status)
        request.send_header("Content-Type", content_type + "; charset=utf-8")
        request.send_header("Content-Length", str(len(body)))
        request.send_header("Cache-Control", "no-store")
        request.send_header("X-Content-Type-Options", "nosniff")
        request.send_header("Referrer-Policy", "no-referrer")
        request.send_header("X-Frame-Options", "DENY")
        request.end_headers()
        try:
            request.wfile.write(body)
        except (ConnectionResetError, BrokenPipeError):
            pass

    def _script(self) -> str:
        schedule = json.dumps(NAVIGATION)
        return """<script>
(() => {
  'use strict';
  const schedule = SCHEDULE;
  let section = null;
  let target = null;
  function locate(name) {
    if (name === 'hero') return document.querySelector('.hero');
    if (name === 'counter-evidence') {
      return Array.from(document.querySelectorAll('#evidence tbody tr')).find(
        row => Array.from(row.cells).some(cell => cell.textContent.trim() === 'EV-008')
      );
    }
    return document.getElementById(name);
  }
  async function tick() {
    try {
      const response = await fetch('./state', {cache: 'no-store'});
      if (!response.ok) throw new Error('Recording stage ended');
      const state = await response.json();
      const next = schedule.filter(([second]) => state.elapsed >= second).at(-1)[1];
      if (next !== section) {
        target = locate(next);
        if (!target) throw new Error('Required section is missing');
        target.scrollIntoView({behavior: 'instant', block: next === 'counter-evidence'
          ? 'center' : 'start'});
        section = next;
      }
      const bounds = target.getBoundingClientRect();
      const inView = bounds.bottom > 80 && bounds.top < window.innerHeight - 40;
      await fetch('./heartbeat', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({section, visible: document.visibilityState === 'visible',
          focused: document.hasFocus(), in_view: inView}),
      });
    } catch (_) {
      // Coordinator health checks fail closed if this page stops reporting.
      return;
    }
    window.setTimeout(tick, 250);
  }
  tick();
})();
</script>""".replace("SCHEDULE", schedule)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._server.shutdown()
            self._server.server_close()
            self._thread.join(timeout=2)

    def __enter__(self) -> RecordingBrowser:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

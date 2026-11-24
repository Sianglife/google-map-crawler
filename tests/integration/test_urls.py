"""Real HTTP and Chrome expansion against a controlled local origin."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from threading import Thread
from urllib.parse import urlsplit

import pytest

from google_map_crawler import expand_short_url, urls
from google_map_crawler.browser import BrowserSession
from google_map_crawler.exceptions import PlaceNotFoundError, UrlExpansionError, UrlExpansionTimeoutError


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("GOOGLE_MAP_CRAWLER_RUN_BROWSER_TESTS") != "1",
        reason="Set GOOGLE_MAP_CRAWLER_RUN_BROWSER_TESTS=1 for local HTTP and real Chrome",
    ),
]


@pytest.fixture
def local_maps(monkeypatch):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            requests.append(path)
            if path in {"/short/http", "/short/second"}:
                self.send_response(301 if path == "/short/http" else 302)
                self.send_header("Location", "/short/second" if path == "/short/http" else "/maps/place/HTTP?entry=fixture#target")
                self.end_headers()
                return
            if path == "/short/js":
                content = '<title>Expanding</title><script>setTimeout(() => location.replace("/maps/place/JavaScript?entry=fixture#target"), 100)</script>'
            elif path == "/short/unsupported":
                content = '<title>Expanding</title><script>location.replace("/unsupported")</script>'
            elif path == "/short/missing":
                content = "<title>Dynamic Link Not Found</title>"
            else:
                content = "<title>Local Maps fixture</title><h1>Expected local place</h1>"
            body = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # The HTTP strategy deliberately closes after headers.

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    origin = f"http://127.0.0.1:{server.server_port}"
    original_classifier = urls._classify_url

    def classify_fixture(url):
        parts = urlsplit(url)
        if f"{parts.scheme}://{parts.netloc}" == origin:
            if parts.path.startswith("/short/"):
                return "short"
            if parts.path.startswith("/maps/place/"):
                return "full"
        return original_classifier(url)

    # Only this test's origin is admitted. Production validation stays unchanged.
    monkeypatch.setattr(urls, "_classify_url", classify_fixture)
    thread.start()
    try:
        yield origin, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.fixture
def owned_sessions(monkeypatch, assert_process_exited):
    resources = []

    class TrackedSession(BrowserSession):
        def __enter__(self):
            driver = super().__enter__()
            pid = driver.capabilities.get("goog:processID")
            assert isinstance(pid, int)
            resources.append((self, driver.service.process, pid))
            return driver

    monkeypatch.setattr(urls, "BrowserSession", TrackedSession)
    yield resources
    for session, process, pid in resources:
        assert session.cleanup_errors == ()
        assert process.poll() is not None, "Owned ChromeDriver is still running"
        assert_process_exited(pid)


def test_real_http_redirects_without_chrome(local_maps, owned_sessions):
    origin, requests = local_maps
    assert expand_short_url(origin + "/short/http", max_retries=0) == origin + "/maps/place/HTTP?entry=fixture#target"
    assert requests == ["/short/http", "/short/second", "/maps/place/HTTP"]
    assert owned_sessions == []


def test_real_chrome_javascript_expansion_and_cleanup(local_maps, owned_sessions):
    origin, requests = local_maps
    assert expand_short_url(origin + "/short/js", timeout=15, max_retries=1) == origin + "/maps/place/JavaScript?entry=fixture#target"
    assert requests.count("/short/js") == 2  # One HTTP attempt and one Chrome attempt.
    assert "/maps/place/JavaScript" in requests and len(owned_sessions) == 1


@pytest.mark.parametrize("path,error_type", [
    ("never", UrlExpansionTimeoutError),
    ("missing", PlaceNotFoundError),
    ("unsupported", UrlExpansionError),
])
def test_real_chrome_failure_cleanup(path, error_type, local_maps, owned_sessions):
    origin, _ = local_maps
    with pytest.raises(error_type):
        expand_short_url(origin + f"/short/{path}", timeout=5, max_retries=1)
    assert len(owned_sessions) == 1

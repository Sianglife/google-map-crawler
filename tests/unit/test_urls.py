"""URL contracts, HTTP resource ownership and the shared expansion budget."""

import errno
from io import BytesIO
import ssl
from urllib.error import HTTPError, URLError

import pytest

from google_map_crawler import expand_short_url
from google_map_crawler import urls
from google_map_crawler.exceptions import (
    InvalidInputError, InvalidMapsUrlError, PageAccessBlockedError,
    PlaceNotFoundError, UrlExpansionError, UrlExpansionTimeoutError,
)


SHORT = "https://maps.app.goo.gl/Example1?g_st=ic"
FULL = "https://www.google.com/maps/place/Example/@25,121,17z/data=!3m1!4b1?entry=ttu#map"


@pytest.fixture
def no_io(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("URL validation must not perform I/O or allocate an ID")

    monkeypatch.setattr(urls, "_make_opener", forbidden)
    monkeypatch.setattr(urls, "BrowserSession", forbidden)
    monkeypatch.setattr("google_map_crawler.identity.uuid4", forbidden)


@pytest.mark.parametrize("url", [
    SHORT, FULL, "http://maps.app.goo.gl/a_B-1/", "https://goo.gl/maps/AbC123?x=1",
    "HTTPS://MAPS.APP.GOO.GL:443/Example", "http://google.com:80/maps/place/台北101",
    "https://google.com/maps/@25,121,16z", "https://google.com/maps?q=台北101",
    "https://www.google.com/maps/?query=Taipei%20101",
    "https://maps.google.com/?cid=123", "https://maps.google.com?q=25,121",
    "https://maps.google.com/maps?saddr=Taipei&daddr=Tainan",
    "https://www.google.com/maps/search/?api=1&query=Taipei%20101",
])
def test_validate_supported_urls_preserves_original(url, no_io):
    assert urls.validate_maps_url(url) is url


@pytest.mark.parametrize("url", [
    None, 1, True, "", " ", "/maps/place/a", "google.com/maps/place/a",
    "ftp://google.com/maps/place/a", "//maps.app.goo.gl/a",
    "https://evil.example/maps/place/a", "https://google.com.evil.example/maps/place/a",
    "https://www.google.com/", "https://google.com/maps", "https://maps.google.com/",
    "https://google.com/maps?q=", "https://google.com/maps?api=1",
    "https://google.com/maps?q=%20", "https://maps.app.goo.gl/",
    "https://maps.app.goo.gl/a/b", "https://goo.gl/a", "https://goo.gl/maps/",
    "https://user@google.com/maps/place/a", "https://:pass@google.com/maps/place/a",
    "https://google.com:8000/maps/place/a", "https://google.com:/maps/place/a",
    "https://google.com:bad/maps/place/a", "https://[broken/maps/place/a",
    "https://google.com\\evil.example/maps/place/a", "https://google.com/maps/a b",
    " https://google.com/maps/place/a", "https://google.com/maps/\na",
    "https://google.com/maps/%", "https://google.com/maps/%XZ",
    "https://google.com/maps/%00a", "https://google.com/maps/%7Fa",
    "https://google.com/maps/%2e%2e/sorry", "https://google.com/maps/%5Ca",
    "https://maps.app.goo.gl/example?name=\ud800",
])
def test_invalid_url_fails_before_io(url, no_io):
    with pytest.raises(InvalidMapsUrlError):
        expand_short_url(url)


def test_full_url_returns_without_io_or_new_id(no_io):
    assert expand_short_url(FULL) is FULL


@pytest.mark.parametrize("options", [
    {"timeout": 0}, {"timeout": True}, {"timeout": float("inf")},
    {"timeout": float("nan")}, {"timeout": "10"},
    {"max_redirects": -1}, {"max_redirects": True}, {"max_redirects": 1.5},
    {"max_retries": -1}, {"max_retries": 4}, {"max_retries": True},
    {"browser_fallback": 1},
])
def test_configuration_is_validated_even_for_full_urls(options, no_io):
    with pytest.raises(InvalidInputError):
        expand_short_url(FULL, **options)


class Response:
    def __init__(self, url, code=200, location=None):
        self.url = url
        self.code = code
        self.headers = {} if location is None else {"Location": location}
        self.closed = False

    def geturl(self):
        return self.url

    def close(self):
        self.closed = True


class Opener:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = []

    def open(self, request, *, timeout):
        self.calls.append((request.full_url, timeout))
        result = next(self.outcomes)
        if isinstance(result, BaseException):
            raise result
        return result


@pytest.fixture
def install_opener(monkeypatch):
    def install(*outcomes):
        opener = Opener(outcomes)
        monkeypatch.setattr(urls, "_make_opener", lambda: opener)
        return opener

    return install


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_http_redirects_preserve_location_and_close_all_responses(status, install_opener):
    redirect, destination = Response(SHORT, status, FULL), Response(FULL)
    opener = install_opener(redirect, destination)
    assert expand_short_url(SHORT) == FULL
    assert [url for url, _ in opener.calls] == [SHORT, FULL]
    assert redirect.closed and destination.closed


def test_multiple_and_relative_redirects(install_opener):
    intermediate = "https://maps.app.goo.gl/second?token=2"
    responses = [Response(SHORT, 302, "/second?token=2"), Response(intermediate, 301, FULL), Response(FULL)]
    opener = install_opener(*responses)
    assert expand_short_url(SHORT, max_redirects=2) == FULL
    assert [url for url, _ in opener.calls] == [SHORT, intermediate, FULL]
    assert all(response.closed for response in responses)


def test_international_text_is_encoded_for_transport_without_rewriting_result(install_opener):
    short = "https://maps.app.goo.gl/example?name=台北"
    full = "https://www.google.com/maps/place/台北101?query=台北#位置"
    encoded_full = "https://www.google.com/maps/place/%E5%8F%B0%E5%8C%97101?query=%E5%8F%B0%E5%8C%97#%E4%BD%8D%E7%BD%AE"
    opener = install_opener(Response(short, 302, full), Response(encoded_full))
    assert expand_short_url(short) == full
    assert [url for url, _ in opener.calls] == ["https://maps.app.goo.gl/example?name=%E5%8F%B0%E5%8C%97", encoded_full]


@pytest.mark.parametrize("location,expected_fragment", [
    ("https://google.com/maps/place/Example", "#keep-location"),
    ("https://google.com/maps/place/Example#replacement", "#replacement"),
    ("https://google.com/maps/place/Example#", ""),
])
def test_http_fragment_inheritance_and_explicit_override(location, expected_fragment, install_opener):
    short = SHORT + "#keep-location"
    expected = "https://google.com/maps/place/Example" + expected_fragment
    install_opener(Response(short, 302, location), Response(expected))
    assert expand_short_url(short) == expected


def test_real_urllib_http_error_response_is_closed(install_opener):
    body = BytesIO(b"redirect body")
    redirect = HTTPError(SHORT, 302, "Found", {"Location": FULL}, body)
    install_opener(redirect, Response(FULL))
    assert expand_short_url(SHORT) == FULL
    assert body.closed


@pytest.mark.parametrize("status,error_type", [
    (404, PlaceNotFoundError), (410, PlaceNotFoundError),
    (401, PageAccessBlockedError), (403, PageAccessBlockedError),
    (400, UrlExpansionError), (501, UrlExpansionError),
])
def test_terminal_http_errors_are_not_retried(status, error_type, install_opener):
    body = BytesIO(b"error body")
    error = HTTPError(SHORT, status, "Failure", {}, body)
    opener = install_opener(error)
    with pytest.raises(error_type) as failure:
        expand_short_url(SHORT)
    assert failure.value.__cause__ is error
    assert len(opener.calls) == 1 and body.closed


@pytest.mark.parametrize("destination,error_type", [
    ("https://consent.google.com/m?continue=maps", PageAccessBlockedError),
    ("https://accounts.google.com/ServiceLogin", PageAccessBlockedError),
    ("https://www.google.com/sorry/index", PageAccessBlockedError),
    ("https://example.com/maps/place/a", UrlExpansionError),
    ("https://[broken", UrlExpansionError),
    ("javascript:alert(1)", UrlExpansionError),
])
def test_redirect_destination_is_validated_before_following(destination, error_type, install_opener):
    response = Response(SHORT, 302, destination)
    opener = install_opener(response)
    with pytest.raises(error_type):
        expand_short_url(SHORT)
    assert len(opener.calls) == 1 and response.closed


@pytest.mark.parametrize("limit,location,message", [
    (0, FULL, "limit"), (10, SHORT, "loop"), (10, None, "Location"),
])
def test_redirect_limit_loop_and_missing_header(limit, location, message, install_opener):
    response = Response(SHORT, 302, location)
    opener = install_opener(response)
    with pytest.raises(UrlExpansionError, match=message):
        expand_short_url(SHORT, max_redirects=limit)
    assert response.closed and len(opener.calls) == 1


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_transient_http_status_is_retried(status, install_opener):
    responses = [Response(SHORT, status), Response(SHORT, 302, FULL), Response(FULL)]
    opener = install_opener(*responses)
    assert expand_short_url(SHORT, max_retries=1) == FULL
    assert len(opener.calls) == 3 and all(response.closed for response in responses)


def test_transient_network_errors_stop_after_four_attempts(install_opener):
    failures = [URLError(ConnectionResetError(errno.ECONNRESET, "reset")) for _ in range(4)]
    opener = install_opener(*failures)
    with pytest.raises(UrlExpansionError) as failure:
        expand_short_url(SHORT)
    assert type(failure.value) is UrlExpansionError
    assert failure.value.__cause__ is failures[-1] and len(opener.calls) == 4


@pytest.mark.parametrize("error", [TimeoutError("socket timeout"), URLError(TimeoutError("timeout"))])
def test_timeout_has_a_distinct_public_error(error, install_opener):
    opener = install_opener(error, error)
    with pytest.raises(UrlExpansionTimeoutError) as failure:
        expand_short_url(SHORT, max_retries=1)
    assert failure.value.__cause__ is error and len(opener.calls) == 2
    assert isinstance(failure.value, UrlExpansionError)


def test_certificate_failure_is_not_retried(install_opener):
    error = URLError(ssl.SSLCertVerificationError("untrusted certificate"))
    opener = install_opener(error)
    with pytest.raises(UrlExpansionError) as failure:
        expand_short_url(SHORT)
    assert failure.value.__cause__ is error and len(opener.calls) == 1


def test_http_and_browser_share_attempt_budget(monkeypatch, install_opener):
    opener = install_opener(Response(SHORT, 503), Response(SHORT))
    browser_calls = []

    def browser(url, budget):
        browser_calls.append((url, budget))
        if len(browser_calls) == 1:
            raise UrlExpansionTimeoutError("temporary page timeout")
        return FULL

    monkeypatch.setattr(urls, "_browser_expand", browser)
    assert expand_short_url(SHORT) == FULL
    assert len(opener.calls) == 2 and len(browser_calls) == 2
    assert browser_calls[0][1] is browser_calls[1][1]


@pytest.mark.parametrize("options", [{"max_retries": 0}, {"browser_fallback": False}])
def test_fallback_is_not_started_without_budget_or_when_disabled(monkeypatch, install_opener, options):
    response = Response(SHORT)
    opener = install_opener(response)

    def forbidden(*args):
        pytest.fail("No browser attempt is allowed")

    monkeypatch.setattr(urls, "_browser_expand", forbidden)
    with pytest.raises(UrlExpansionError):
        expand_short_url(SHORT, **options)
    assert len(opener.calls) == 1 and response.closed


def test_fallback_uses_last_supported_short_destination(monkeypatch, install_opener):
    legacy = "https://goo.gl/maps/NextLink"
    install_opener(Response(SHORT, 302, legacy), Response(legacy))
    received = []
    monkeypatch.setattr(urls, "_browser_expand", lambda url, budget: received.append(url) or FULL)
    assert expand_short_url(SHORT, max_retries=1) == FULL
    assert received == [legacy]


def test_terminal_browser_failure_is_not_retried(monkeypatch, install_opener):
    install_opener(Response(SHORT))
    failure = PageAccessBlockedError("verification required")
    calls = []

    def browser(*args):
        calls.append(args)
        raise failure

    monkeypatch.setattr(urls, "_browser_expand", browser)
    with pytest.raises(PageAccessBlockedError) as result:
        expand_short_url(SHORT)
    assert result.value is failure and len(calls) == 1


def test_remaining_timeout_decreases_across_http_and_browser(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(urls, "monotonic", lambda: clock[0])
    responses = iter([Response(SHORT, 302, "https://goo.gl/maps/next"), Response("https://goo.gl/maps/next")])
    timeouts = []

    class TimedOpener:
        def open(self, request, *, timeout):
            timeouts.append(timeout)
            clock[0] += 2
            return next(responses)

    monkeypatch.setattr(urls, "_make_opener", TimedOpener)
    monkeypatch.setattr(urls, "_browser_expand", lambda url, budget: timeouts.append(budget.remaining()) or FULL)
    assert expand_short_url(SHORT, timeout=10) == FULL
    assert timeouts == [10, 8, 6]


def test_expired_deadline_cannot_return_success_and_closes_response(monkeypatch):
    clock = [0.0]
    response = Response(FULL)
    monkeypatch.setattr(urls, "monotonic", lambda: clock[0])

    class ExpiringOpener:
        def open(self, request, *, timeout):
            clock[0] += timeout
            return response

    monkeypatch.setattr(urls, "_make_opener", ExpiringOpener)
    with pytest.raises(UrlExpansionTimeoutError):
        expand_short_url(SHORT, timeout=1)
    assert response.closed


def test_deadline_expiry_retains_the_last_network_failure(monkeypatch):
    clock = [0.0]
    original = URLError(TimeoutError("socket timeout"))
    monkeypatch.setattr(urls, "monotonic", lambda: clock[0])

    class ExpiringOpener:
        def open(self, request, *, timeout):
            clock[0] += timeout
            raise original

    monkeypatch.setattr(urls, "_make_opener", ExpiringOpener)
    with pytest.raises(UrlExpansionTimeoutError) as failure:
        expand_short_url(SHORT, timeout=1)
    assert failure.value.__cause__ is original


def test_redirect_limit_is_cumulative_across_retries(install_opener):
    intermediate = "https://goo.gl/maps/next"
    responses = [Response(SHORT, 302, intermediate), Response(intermediate, 503), Response(SHORT, 302, intermediate)]
    opener = install_opener(*responses)
    with pytest.raises(UrlExpansionError, match="limit"):
        expand_short_url(SHORT, max_redirects=1)
    assert len(opener.calls) == 3 and all(response.closed for response in responses)


@pytest.mark.parametrize("during", ["timeout-setting", "navigation"])
@pytest.mark.parametrize("timeout", [False, True])
def test_browser_command_errors_are_classified_and_session_closes(monkeypatch, during, timeout):
    from selenium.common.exceptions import TimeoutException, WebDriverException

    original = TimeoutException("page timeout") if timeout else WebDriverException("browser failure")
    closed = []

    class Driver:
        def set_page_load_timeout(self, seconds):
            if during == "timeout-setting":
                raise original

        def get(self, url):
            raise original

    class Session:
        def __init__(self, config):
            pass

        def __enter__(self):
            return Driver()

        def __exit__(self, *args):
            closed.append(True)

    monkeypatch.setattr(urls, "BrowserSession", Session)
    expected = UrlExpansionTimeoutError if timeout else UrlExpansionError
    with pytest.raises(expected) as failure:
        urls._browser_expand(SHORT, urls._Budget(urls.monotonic() + 10, 10))
    assert failure.value.__cause__ is original and closed == [True]

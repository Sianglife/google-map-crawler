"""Validate Maps URLs and expand short links using a shared operation budget."""

from contextlib import closing
from dataclasses import dataclass
import errno
import re
import socket
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ._control import control_scope
from .browser import BrowserConfig, BrowserSession
from .exceptions import (
    InvalidInputError,
    InvalidMapsUrlError,
    PageAccessBlockedError,
    PlaceNotFoundError,
    UrlExpansionError,
    UrlExpansionTimeoutError,
)
from .validation import validate_count


_REDIRECTS = {301, 302, 303, 307, 308}
_TRANSIENT_STATUS = {429, 500, 502, 503, 504}
_LOCATION_PARAMETERS = {"q", "query", "cid", "ll", "saddr", "daddr"}


def _classify_url(url: str) -> str:
    if (
        not isinstance(url, str) or not url
        or any(
            character.isspace() or ord(character) < 32 or ord(character) == 127
            or 0xD800 <= ord(character) <= 0xDFFF
            for character in url
        )
        or "\\" in url or re.search(r"%(?![0-9a-fA-F]{2})", url)
    ):
        raise InvalidMapsUrlError("url must be a supported Google Maps URL")
    try:
        parts = urlsplit(url)
        if (
            parts.scheme not in {"http", "https"}
            or parts.username is not None or parts.password is not None
        ):
            raise ValueError("Unsupported scheme or credentials")
        if parts.port not in (None, 443 if parts.scheme == "https" else 80) or parts.netloc.endswith(":"):
            raise ValueError("Unsupported port")
        path = unquote(parts.path)
        if (
            "\\" in path or any(part in {".", ".."} for part in path.split("/"))
            or any(ord(c) < 32 or ord(c) == 127 for c in path)
        ):
            raise ValueError("Invalid path")
        if parts.hostname == "maps.app.goo.gl" and re.fullmatch(r"/[A-Za-z0-9_-]+/?", path):
            return "short"
        if parts.hostname == "goo.gl" and re.fullmatch(r"/maps/[A-Za-z0-9_-]+/?", path):
            return "short"
        if parts.hostname in {"google.com", "www.google.com", "maps.google.com"}:
            if path.startswith("/maps/") and path[len("/maps/"):].strip("/"):
                return "full"
            roots = {"/maps", "/maps/"}
            if parts.hostname == "maps.google.com":
                roots.update({"", "/"})
            if path in roots and any(
                key in _LOCATION_PARAMETERS and any(value.strip() for value in values)
                for key, values in parse_qs(parts.query).items()
            ):
                return "full"
    except ValueError as error:
        raise InvalidMapsUrlError("url must be a supported Google Maps URL") from error
    raise InvalidMapsUrlError("url must be a supported Google Maps URL")


def validate_maps_url(url: str) -> str:
    """Validate supported syntax without I/O or rewriting the URL."""
    _classify_url(url)
    return url


def _is_access_blocked(url: str) -> bool:
    parts = urlsplit(url)
    return parts.hostname in {"accounts.google.com", "consent.google.com"} or (
        parts.hostname in {"google.com", "www.google.com"}
        and parts.path.startswith(("/sorry", "/signin", "/ServiceLogin"))
    )


def _destination_kind(url: str) -> str:
    try:
        if _is_access_blocked(url):
            raise PageAccessBlockedError("Maps navigation requires access approval or verification")
        return _classify_url(url)
    except (InvalidMapsUrlError, ValueError) as error:
        raise UrlExpansionError("Redirected to an unsupported Maps destination") from error


@dataclass
class _Budget:
    deadline: float
    max_redirects: int
    redirects: int = 0

    def remaining(self) -> float:
        remaining = self.deadline - monotonic()
        if remaining <= 0:
            raise UrlExpansionTimeoutError("URL expansion time budget expired")
        return remaining


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


class _TransientHttpError(Exception):
    pass


def _make_opener():
    return build_opener(_NoRedirect())


def _http_expand(url: str, budget: _Budget, opener) -> str:
    current = url
    visited = set()
    while True:
        if current in visited:
            raise UrlExpansionError("HTTP redirect loop detected")
        visited.add(current)
        _destination_kind(current)
        # Encode international text for transport, preserving the returned spelling.
        request_url = quote(current, safe=":/?#[]@!$&'()*+,;=%")
        request = Request(request_url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; GoogleMapCrawler/0.1)",
        })
        try:
            response = opener.open(request, timeout=budget.remaining())
        except HTTPError as error:
            response = error
        with closing(response):
            budget.remaining()
            code = response.code
            if code in _REDIRECTS:
                location = response.headers.get("Location")
                if not location:
                    raise UrlExpansionError("HTTP redirect has no Location header")
                try:
                    destination = urljoin(current, location)
                    # HTTP Location without '#' inherits the original fragment.
                    fragment = urlsplit(current).fragment
                    if "#" not in location and fragment:
                        destination += "#" + fragment
                except ValueError as error:
                    raise UrlExpansionError("Invalid HTTP redirect destination") from error
                _destination_kind(destination)
                if budget.redirects >= budget.max_redirects:
                    raise UrlExpansionError("HTTP redirect limit reached")
                budget.redirects += 1
                current = destination
                continue
            if code in {404, 410}:
                raise PlaceNotFoundError(f"Maps link is unavailable (HTTP {code})") from (
                    response if isinstance(response, HTTPError) else None
                )
            if code in {401, 403}:
                raise PageAccessBlockedError(f"Maps link access denied (HTTP {code})") from (
                    response if isinstance(response, HTTPError) else None
                )
            if code in _TRANSIENT_STATUS:
                raise _TransientHttpError(f"Temporary HTTP failure ({code})") from (
                    response if isinstance(response, HTTPError) else None
                )
            if not 200 <= code < 300:
                raise UrlExpansionError(f"Unexpected HTTP status ({code})") from (
                    response if isinstance(response, HTTPError) else None
                )
            # Do not download the page body; final response headers suffice here.
            response_url = response.geturl()
            result = current if response_url == request_url else response_url
            _destination_kind(result)
            return result


def _browser_expand(url: str, budget: _Budget) -> str:
    from selenium.common.exceptions import JavascriptException, TimeoutException, WebDriverException
    from selenium.webdriver.support.ui import WebDriverWait

    remaining = budget.remaining()
    config = BrowserConfig(page_load_timeout=remaining, wait_timeout=remaining, max_retries=0)
    with BrowserSession(config) as driver:
        def destination_ready(_):
            budget.remaining()
            current = driver.current_url
            if current == "about:blank":
                return False
            kind = _destination_kind(current)
            state = driver.execute_script("return [document.readyState, document.documentURI]")
            if state[1].startswith("chrome-error:"):
                raise UrlExpansionError("Browser could not load the destination")
            if driver.title in {"Dynamic Link Not Found", "Error 404 (Not Found)!!1"}:
                raise PlaceNotFoundError("Browser displayed an unavailable-link page")
            if kind == "full" and state[0] in {"interactive", "complete"}:
                return current
            return False

        try:
            driver.set_page_load_timeout(budget.remaining())
            driver.get(url)
            result = WebDriverWait(
                driver, budget.remaining(), poll_frequency=0.1,
                ignored_exceptions=(JavascriptException,),
            ).until(destination_ready)
            budget.remaining()
            return result
        except TimeoutException as error:
            raise UrlExpansionTimeoutError("Browser URL expansion timed out") from error
        except WebDriverException as error:
            raise UrlExpansionError("Browser URL expansion failed") from error


def _is_transient(error: BaseException) -> bool:
    if isinstance(error, (_TransientHttpError, UrlExpansionTimeoutError, TimeoutError)):
        return True
    reason = error.reason if isinstance(error, URLError) else error
    return isinstance(reason, TimeoutError) or (
        isinstance(reason, OSError) and reason.errno in {
            errno.ECONNRESET, errno.ECONNABORTED, errno.ECONNREFUSED,
            errno.ETIMEDOUT, socket.EAI_AGAIN,
        }
    )


def expand_short_url(
    url: str, *, timeout: float = 30, max_redirects: int = 10,
    max_retries: int = 3, browser_fallback: bool = True,
) -> str:
    """Expand a short link; HTTP and browser attempts share one finite budget."""
    kind = _classify_url(url)
    config = BrowserConfig(page_load_timeout=timeout, wait_timeout=timeout, max_retries=max_retries)
    validate_count(max_redirects, name="max_redirects")
    if not isinstance(browser_fallback, bool):
        raise InvalidInputError("browser_fallback must be a boolean")
    if kind == "full":
        return url

    with control_scope("url"):
        return _expand_short_url(url, config, max_redirects, browser_fallback)


def _expand_short_url(url, config, max_redirects, browser_fallback):
    budget = _Budget(monotonic() + config.page_load_timeout, max_redirects)
    opener = _make_opener()
    phase = "http"
    current = url
    last_error = None
    for _ in range(config.max_retries + 1):
        try:
            budget.remaining()
        except UrlExpansionTimeoutError as error:
            raise error from last_error
        try:
            if phase == "http":
                result = _http_expand(current, budget, opener)
            else:
                result = _browser_expand(current, budget)
            budget.remaining()
            if _destination_kind(result) == "full":
                return result
            if not browser_fallback:
                raise UrlExpansionError("HTTP did not expand the short URL and browser fallback is disabled")
            current, phase = result, "browser"
            last_error = UrlExpansionError("No remaining attempt for browser fallback")
        except (_TransientHttpError, URLError, OSError, UrlExpansionTimeoutError) as error:
            if not _is_transient(error):
                raise UrlExpansionError("URL expansion request failed") from error
            last_error = error

    if isinstance(last_error, (TimeoutError, UrlExpansionTimeoutError)) or (
        isinstance(last_error, URLError) and isinstance(last_error.reason, TimeoutError)
    ):
        raise UrlExpansionTimeoutError("URL expansion attempts timed out") from last_error
    raise UrlExpansionError("URL expansion attempts exhausted") from last_error

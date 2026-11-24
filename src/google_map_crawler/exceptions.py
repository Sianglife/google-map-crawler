"""Errors exposed by the crawler, independent of browser implementations."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .matching import PlaceComparison


class CrawlerError(Exception):
    """Base class for errors raised by this package."""


class InvalidInputError(CrawlerError):
    """A supplied argument or model field is invalid."""


class InvalidLocationIdError(InvalidInputError):
    """A location ID is not a UUID v4 string."""


class InvalidMapsUrlError(InvalidInputError):
    """A supplied URL is not a supported Google Maps URL."""


class PlaceNotFoundError(CrawlerError):
    """A Maps link is unavailable or the requested place cannot be found."""


class PageWaitError(CrawlerError):
    """A page wait failed; diagnostic context does not perform driver I/O."""

    def __init__(
        self, message: str = "Page wait failed", *, operation: str | None = None,
        locator: tuple[str, str] | None = None, state: str | None = None,
        timeout: float | None = None, last_error: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.locator = locator
        self.state = state
        self.timeout = timeout
        self.last_error = last_error


class PageLoadTimeoutError(PageWaitError):
    """A page or required element did not become ready within its timeout."""


class OperationRetryError(CrawlerError):
    """A bounded operation failed, without silently returning partial results."""

    def __init__(
        self, message: str, *, operation: str, attempts: int, max_retries: int,
        timeout: float, reason: str, locator: tuple[str, str] | None = None,
        last_error: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.attempts = attempts
        self.max_retries = max_retries
        self.timeout = timeout
        self.reason = reason
        self.locator = locator
        self.last_error = last_error


class OperationRetryTimeoutError(OperationRetryError):
    """An operation and its recovery exhausted their shared time budget."""


class ParseError(CrawlerError):
    """Required page data could not be interpreted."""


class BrowserStartError(CrawlerError):
    """The browser could not be created or initially configured."""


class BrowserCleanupError(CrawlerError):
    """One or more attempts to release owned browser resources failed."""

    def __init__(
        self,
        message: str = "Failed to release browser resources",
        *,
        errors: Iterable[BaseException] = (),
    ) -> None:
        super().__init__(message)
        self.errors = tuple(errors)


class UrlExpansionError(CrawlerError):
    """A short URL could not be expanded to its destination."""


class UrlExpansionTimeoutError(UrlExpansionError):
    """URL expansion ran out of time or a network/page operation timed out."""


class PageAccessBlockedError(CrawlerError):
    """A page requires authentication or verification before it can be used."""


class AmbiguousPlaceMatchError(CrawlerError):
    """Multiple qualifying places tie for the fewest differing fields."""

    def __init__(
        self,
        message: str = "Multiple qualifying places tie for the fewest differing fields",
        *,
        matches: Iterable[PlaceComparison] = (),
    ) -> None:
        super().__init__(message)
        self.matches = tuple(matches)

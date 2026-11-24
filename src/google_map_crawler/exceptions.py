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


class PageLoadTimeoutError(CrawlerError):
    """A page or required element did not become ready within its timeout."""


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

"""Errors exposed by the crawler, independent of browser implementations."""


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


class AmbiguousPlaceMatchError(CrawlerError):
    """More than one existing place satisfies the matching rules."""

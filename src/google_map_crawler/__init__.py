"""Offline data contracts and tools for a Google Maps crawler library."""

from .exceptions import (
    AmbiguousPlaceMatchError,
    BrowserCleanupError,
    BrowserStartError,
    CrawlerError,
    InvalidInputError,
    InvalidLocationIdError,
    InvalidMapsUrlError,
    PageLoadTimeoutError,
    PageAccessBlockedError,
    ParseError,
    PlaceNotFoundError,
    UrlExpansionError,
)
from .identity import (
    create_location_id,
    rebind_location_id,
    resolve_location_id,
    validate_location_id,
)
from .matching import PlaceComparison, compare_places, find_place_match
from .models import PlaceDetail, PlaceSearchResult, Review, ReviewSummary, ReviewTag
from .validation import validate_count, validate_non_empty_string


__all__ = [
    "AmbiguousPlaceMatchError",
    "BrowserCleanupError",
    "BrowserStartError",
    "CrawlerError",
    "InvalidInputError",
    "InvalidLocationIdError",
    "InvalidMapsUrlError",
    "PageLoadTimeoutError",
    "PageAccessBlockedError",
    "ParseError",
    "PlaceNotFoundError",
    "UrlExpansionError",
    "PlaceComparison",
    "PlaceDetail",
    "PlaceSearchResult",
    "Review",
    "ReviewSummary",
    "ReviewTag",
    "create_location_id",
    "compare_places",
    "find_place_match",
    "rebind_location_id",
    "resolve_location_id",
    "validate_location_id",
    "validate_count",
    "validate_non_empty_string",
]

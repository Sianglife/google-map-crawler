"""Data contracts, matching tools and Maps URL expansion for the crawler library."""

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
    UrlExpansionTimeoutError,
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
from .urls import expand_short_url


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
    "UrlExpansionTimeoutError",
    "PlaceComparison",
    "PlaceDetail",
    "PlaceSearchResult",
    "Review",
    "ReviewSummary",
    "ReviewTag",
    "create_location_id",
    "expand_short_url",
    "compare_places",
    "find_place_match",
    "rebind_location_id",
    "resolve_location_id",
    "validate_location_id",
    "validate_count",
    "validate_non_empty_string",
]

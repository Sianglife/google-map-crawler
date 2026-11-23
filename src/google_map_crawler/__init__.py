"""Offline data contracts and tools for a Google Maps crawler library."""

from .exceptions import (
    AmbiguousPlaceMatchError,
    CrawlerError,
    InvalidInputError,
    InvalidLocationIdError,
    InvalidMapsUrlError,
    PageLoadTimeoutError,
    ParseError,
    PlaceNotFoundError,
)
from .identity import create_location_id, resolve_location_id, validate_location_id
from .models import PlaceDetail, PlaceSearchResult, Review, ReviewSummary, ReviewTag
from .validation import validate_count, validate_non_empty_string


__all__ = [
    "AmbiguousPlaceMatchError",
    "CrawlerError",
    "InvalidInputError",
    "InvalidLocationIdError",
    "InvalidMapsUrlError",
    "PageLoadTimeoutError",
    "ParseError",
    "PlaceNotFoundError",
    "PlaceDetail",
    "PlaceSearchResult",
    "Review",
    "ReviewSummary",
    "ReviewTag",
    "create_location_id",
    "resolve_location_id",
    "validate_location_id",
    "validate_count",
    "validate_non_empty_string",
]

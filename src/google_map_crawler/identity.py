"""Random internal location IDs; Maps URLs are handled separately."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, TypeVar
from uuid import UUID, uuid4

from .exceptions import InvalidInputError, InvalidLocationIdError

if TYPE_CHECKING:
    from .models import PlaceSearchResult, Review, ReviewSummary, ReviewTag

_RecordT = TypeVar("_RecordT", bound="PlaceSearchResult | ReviewSummary | Review | ReviewTag")


def create_location_id() -> str:
    """Create an ID for a new place record, independently of its URL or fields."""
    return str(uuid4())


def validate_location_id(location_id: str) -> str:
    """Validate a UUID v4 string without rewriting its representation."""
    message = "location_id must be a UUID v4 string"
    if not isinstance(location_id, str):
        raise InvalidLocationIdError(message)
    try:
        parsed = UUID(location_id)
    except ValueError as error:
        raise InvalidLocationIdError(message) from error
    if parsed.version != 4:
        raise InvalidLocationIdError(message)
    return location_id


def resolve_location_id(location_id: str | None = None) -> str:
    """Keep a supplied ID, or generate one only when no ID was supplied."""
    if location_id is None:
        return create_location_id()
    return validate_location_id(location_id)


def rebind_location_id(record: _RecordT, location_id: str) -> _RecordT:
    """Return a validated copy, including review/tag copies for a summary."""
    # Models already import the ID validators; defer this import to avoid a cycle.
    from .models import PlaceSearchResult, Review, ReviewSummary, ReviewTag

    validate_location_id(location_id)
    if not isinstance(record, (PlaceSearchResult, Review, ReviewSummary, ReviewTag)):
        raise InvalidInputError("record must be one of the five crawler data models")
    validate_location_id(record.location_id)
    if isinstance(record, ReviewSummary):
        # Validate existing associations before changing them; don't absorb unrelated children.
        validated = replace(record)
        return replace(
            validated,
            location_id=location_id,
            reviews=[rebind_location_id(item, location_id) for item in validated.reviews],
            tags=[rebind_location_id(item, location_id) for item in validated.tags],
        )
    return replace(record, location_id=location_id)

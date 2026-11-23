"""Random internal location IDs; Maps URLs are handled separately."""

from uuid import UUID, uuid4

from .exceptions import InvalidLocationIdError


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

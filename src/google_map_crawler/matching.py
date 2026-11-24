"""Directional place comparison and selection without storage or browser access."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields
from math import isfinite
from types import UnionType
from typing import Union, get_args, get_origin, get_type_hints

from .exceptions import AmbiguousPlaceMatchError, InvalidInputError
from .identity import validate_location_id
from .models import PlaceDetail
from .validation import validate_non_empty_string


_PLACE_TYPES = get_type_hints(PlaceDetail)
_FIELD_TYPES = {
    item.name: _PLACE_TYPES[item.name]
    for item in fields(PlaceDetail)
    if item.name not in {"location_id", "fetched_at"}
}


@dataclass(frozen=True, kw_only=True)
class PlaceComparison:
    """An immutable diagnostic result; counts are derived from field names."""

    existing_location_id: str
    compared_fields: tuple[str, ...]
    different_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        validate_location_id(self.existing_location_id)
        for name in ("compared_fields", "different_fields"):
            value = getattr(self, name)
            if not isinstance(value, tuple) or any(
                not isinstance(item, str) or not item for item in value
            ):
                raise InvalidInputError(f"{name} must be a tuple of field names")
            if len(set(value)) != len(value):
                raise InvalidInputError(f"{name} must not contain duplicate fields")
        if not set(self.different_fields).issubset(self.compared_fields):
            raise InvalidInputError("different_fields must be part of compared_fields")

    @property
    def difference_count(self) -> int:
        return len(self.different_fields)

    @property
    def is_match(self) -> bool:
        return self.difference_count <= 2


def _is_empty(value: object) -> bool:
    return (
        value is None
        or (isinstance(value, str) and not value.strip())
        or (isinstance(value, list) and not value)
    )


def _matches_type(value: object, expected: object) -> bool:
    origin = get_origin(expected)
    if origin in (Union, UnionType):
        return any(_matches_type(value, option) for option in get_args(expected))
    if origin is list:
        return isinstance(value, list) and all(
            _matches_type(item, get_args(expected)[0]) for item in value
        )
    if expected is float:
        return not isinstance(value, bool) and isinstance(value, (int, float))
    if expected is int:
        return not isinstance(value, bool) and isinstance(value, int)
    return isinstance(expected, type) and isinstance(value, expected)


def _snapshot(
    record: PlaceDetail | Mapping[str, object], *, name: str, allow_mapping: bool
) -> tuple[str, dict[str, object]]:
    if isinstance(record, PlaceDetail):
        location_id = record.location_id
        values = {
            key: getattr(record, key) for key in _FIELD_TYPES if hasattr(record, key)
        }
    elif allow_mapping and isinstance(record, Mapping):
        location_id = record.get("location_id")
        values = {key: record[key] for key in _FIELD_TYPES if key in record}
    else:
        expected = "PlaceDetail or mapping" if allow_mapping else "PlaceDetail"
        raise InvalidInputError(f"{name} must be a {expected}")

    validate_location_id(location_id)
    if not allow_mapping:
        validate_non_empty_string(values.get("maps_url"), name="incoming.maps_url")
    for key, value in values.items():
        if _is_empty(value):
            continue
        if not _matches_type(value, _FIELD_TYPES[key]):
            raise InvalidInputError(f"{name}.{key} has an invalid field type")
        if key == "rating":
            if not 0 <= value <= 5 or not isfinite(value) or value != round(value, 1):
                raise InvalidInputError(
                    f"{name}.rating must be between 0 and 5 with at most one decimal place"
                )
    # All current list fields contain strings, so copying each container is enough.
    snapshot = {
        key: list(value) if isinstance(value, list) else value
        for key, value in values.items()
    }
    return location_id, snapshot


def _compare_snapshot(
    existing: PlaceDetail | Mapping[str, object], incoming: dict[str, object]
) -> PlaceComparison:
    location_id, previous = _snapshot(existing, name="existing", allow_mapping=True)
    compared = tuple(key for key, value in previous.items() if not _is_empty(value))
    different = tuple(
        key
        for key in compared
        if _is_empty(incoming.get(key)) or previous[key] != incoming.get(key)
    )
    return PlaceComparison(
        existing_location_id=location_id,
        compared_fields=compared,
        different_fields=different,
    )


def compare_places(
    existing: PlaceDetail | Mapping[str, object], incoming: PlaceDetail
) -> PlaceComparison:
    """Compare existing non-empty fields with incoming data; never modify either."""
    _, snapshot = _snapshot(incoming, name="incoming", allow_mapping=False)
    return _compare_snapshot(existing, snapshot)


def find_place_match(
    incoming: PlaceDetail,
    candidates: Iterable[PlaceDetail | Mapping[str, object]],
) -> PlaceComparison | None:
    """Return the unique fewest-difference match after checking every candidate."""
    _, snapshot = _snapshot(incoming, name="incoming", allow_mapping=False)
    if isinstance(candidates, (str, bytes, Mapping)):
        raise InvalidInputError("candidates must be an iterable of existing records")
    try:
        iterator = iter(candidates)
    except TypeError as error:
        raise InvalidInputError(
            "candidates must be an iterable of existing records"
        ) from error

    best: list[PlaceComparison] = []
    for candidate in iterator:
        result = _compare_snapshot(candidate, snapshot)
        if not result.is_match:
            continue
        if not best or result.difference_count < best[0].difference_count:
            best = [result]
        elif result.difference_count == best[0].difference_count:
            best.append(result)

    if len(best) > 1:
        raise AmbiguousPlaceMatchError(matches=best)
    return best[0] if best else None

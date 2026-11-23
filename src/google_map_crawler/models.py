"""Typed crawler results, validated on construction and independent of storage."""

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from math import isfinite
from typing import Any, TypeVar

from .exceptions import InvalidInputError
from .identity import validate_location_id
from .validation import validate_count, validate_non_empty_string


_T = TypeVar("_T")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise InvalidInputError("fetched_at must be a timezone-aware datetime")
    return value.astimezone(UTC)


def _optional_text(value: str | None, *, name: str) -> None:
    if value is not None and not isinstance(value, str):
        raise InvalidInputError(f"{name} must be a string or None")


def _optional_rating(
    value: float | None, *, name: str, one_decimal: bool = False
) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidInputError(f"{name} must be a number between 0 and 5 or None")
    if not 0 <= value <= 5 or not isfinite(value):
        raise InvalidInputError(f"{name} must be a finite number between 0 and 5")
    result = float(value)
    if one_decimal and result != round(result, 1):
        raise InvalidInputError(f"{name} must have at most one decimal place")
    return result


def _checked_list(value: list[_T], *, name: str, item_type: type[_T]) -> list[_T]:
    if not isinstance(value, list) or any(
        not isinstance(item, item_type) for item in value
    ):
        raise InvalidInputError(f"{name} must be a list of {item_type.__name__} objects")
    return list(value)


def _json_compatible(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, list):
        return [_json_compatible(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_compatible(item) for key, item in value.items()}
    return value


@dataclass(kw_only=True)
class _LocationRecord:
    location_id: str
    fetched_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        validate_location_id(self.location_id)
        self.fetched_at = _as_utc(self.fetched_at)

    def to_dict(self) -> dict[str, Any]:
        """Return detached JSON-compatible data; no files or connections are used."""
        return _json_compatible(asdict(self))


@dataclass(kw_only=True)
class PlaceSearchResult(_LocationRecord):
    """Fields available from a search listing, without a detail-page fetch."""

    maps_url: str
    name: str | None = None
    category: str | None = None
    address: str | None = None
    rating: float | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        validate_non_empty_string(self.maps_url, name="maps_url")
        for name in ("name", "category", "address"):
            _optional_text(getattr(self, name), name=name)
        self.rating = _optional_rating(self.rating, name="rating", one_decimal=True)


@dataclass(kw_only=True)
class PlaceDetail(PlaceSearchResult):
    """Place details; opening hours and price level retain their original text."""

    price_level: str | None = None
    website: str | None = None
    phone: str | None = None
    opening_hours: list[str] = field(default_factory=list)
    photos: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__post_init__()
        for name in ("price_level", "website", "phone"):
            _optional_text(getattr(self, name), name=name)
        self.opening_hours = _checked_list(
            self.opening_hours, name="opening_hours", item_type=str
        )
        self.photos = _checked_list(self.photos, name="photos", item_type=str)


@dataclass(kw_only=True)
class Review(_LocationRecord):
    """A review, including valid rating-only entries without text or photos."""

    author: str | None = None
    author_info: str | None = None
    rating: int | None = None
    content: str | None = None
    photos: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__post_init__()
        for name in ("author", "author_info", "content"):
            _optional_text(getattr(self, name), name=name)
        if self.rating is not None and (
            isinstance(self.rating, bool) or not isinstance(self.rating, int)
        ):
            raise InvalidInputError("rating must be an integer or None")
        self.photos = _checked_list(self.photos, name="photos", item_type=str)


@dataclass(kw_only=True)
class ReviewTag(_LocationRecord):
    """A displayed review tag and its optional count."""

    text: str | None = None
    count: int | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        _optional_text(self.text, name="text")
        if self.count is not None:
            validate_count(self.count, name="count")


@dataclass(kw_only=True)
class ReviewSummary(_LocationRecord):
    """Displayed totals and the reviews actually fetched for one place."""

    average_rating: float | None = None
    total_count: int | None = None
    tags: list[ReviewTag] = field(default_factory=list)
    reviews: list[Review] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__post_init__()
        self.average_rating = _optional_rating(
            self.average_rating, name="average_rating"
        )
        if self.total_count is not None:
            validate_count(self.total_count, name="total_count")
        self.tags = _checked_list(self.tags, name="tags", item_type=ReviewTag)
        self.reviews = _checked_list(self.reviews, name="reviews", item_type=Review)
        for name in ("tags", "reviews"):
            if any(item.location_id != self.location_id for item in getattr(self, name)):
                raise InvalidInputError(f"{name} must use the summary's location_id")

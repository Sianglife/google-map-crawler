"""Contracts for generating new IDs and preserving existing place identity."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from google_map_crawler.exceptions import InvalidInputError, InvalidLocationIdError
from google_map_crawler.identity import (
    create_location_id,
    rebind_location_id,
    resolve_location_id,
    validate_location_id,
)
from google_map_crawler.models import PlaceDetail, PlaceSearchResult, Review, ReviewSummary, ReviewTag


LOCATION_ID = "8f2a79bd-b660-4c7e-a9df-f0e9bde31650"


def test_new_records_receive_distinct_uuid4_strings():
    first = create_location_id()
    second = resolve_location_id()

    assert UUID(first).version == UUID(second).version == 4
    assert str(UUID(first)) == first
    assert first != second


@pytest.mark.parametrize("existing", [LOCATION_ID, LOCATION_ID.upper()])
def test_existing_id_is_preserved_without_generating_a_replacement(existing, monkeypatch):
    def unexpected_generation():
        pytest.fail("An existing ID must not be replaced")

    monkeypatch.setattr("google_map_crawler.identity.uuid4", unexpected_generation)

    assert resolve_location_id(existing) == existing
    assert validate_location_id(existing) == existing


@pytest.mark.parametrize(
    "invalid",
    [None, "", "   ", "share-url-token", 42, UUID(LOCATION_ID),
     "00000000-0000-0000-0000-000000000000",
     "8f2a79bd-b660-1c7e-a9df-f0e9bde31650"],
)
def test_invalid_id_raises_a_specific_input_error(invalid):
    with pytest.raises(InvalidLocationIdError, match="location_id") as caught:
        validate_location_id(invalid)

    assert isinstance(caught.value, InvalidInputError)


def test_invalid_supplied_id_is_not_silently_replaced():
    with pytest.raises(InvalidLocationIdError):
        resolve_location_id("")


TARGET_ID = "9c01d47f-27be-4bc0-84f7-22df0fbdc291"
FETCHED_AT = datetime(2026, 11, 23, 6, 30, tzinfo=UTC)


def related_records():
    review = Review(
        location_id=LOCATION_ID, fetched_at=FETCHED_AT, rating=5, photos=["photo-1"]
    )
    tag = ReviewTag(location_id=LOCATION_ID, fetched_at=FETCHED_AT, text="美食", count=2)
    return [
        PlaceSearchResult(location_id=LOCATION_ID, fetched_at=FETCHED_AT, maps_url="url", name="地點"),
        PlaceDetail(location_id=LOCATION_ID, fetched_at=FETCHED_AT, maps_url="url", photos=["place-photo"], opening_hours=["休息"]),
        review,
        tag,
        ReviewSummary(location_id=LOCATION_ID, fetched_at=FETCHED_AT, total_count=100, reviews=[review], tags=[tag]),
    ]


@pytest.mark.parametrize("index", range(5))
@pytest.mark.parametrize("target", [TARGET_ID, LOCATION_ID])
def test_rebind_returns_same_type_copies_and_preserves_all_other_data(index, target):
    record = related_records()[index]
    before = record.to_dict()
    expected = record.to_dict()
    expected["location_id"] = target
    if isinstance(record, ReviewSummary):
        expected["reviews"][0]["location_id"] = target
        expected["tags"][0]["location_id"] = target

    result = rebind_location_id(record, target)

    assert result is not record
    assert type(result) is type(record)
    assert result.to_dict() == expected
    assert result.fetched_at == FETCHED_AT
    assert record.to_dict() == before


def test_rebind_detaches_summary_children_and_all_mutable_lists():
    records = related_records()
    place = records[1]
    original = records[-1]
    summary = rebind_location_id(original, TARGET_ID)
    updated_place = rebind_location_id(place, TARGET_ID)

    assert summary.reviews[0] is not original.reviews[0]
    assert summary.tags[0] is not original.tags[0]
    summary.reviews[0].photos.append("new-photo")
    summary.reviews[0].content = "changed"
    summary.tags[0].text = "changed"
    summary.reviews.clear()
    summary.tags.clear()
    updated_place.photos.clear()
    updated_place.opening_hours.clear()

    assert original.reviews[0].photos == ["photo-1"]
    assert original.reviews[0].content is None
    assert original.tags[0].text == "美食"
    assert place.photos == ["place-photo"]
    assert place.opening_hours == ["休息"]


def test_rebind_failure_does_not_partially_update_an_input():
    original = related_records()[-1]
    original.reviews.append(Review(location_id=LOCATION_ID, photos=["valid"]))
    original.reviews[-1].photos = None
    before = original.to_dict()

    with pytest.raises(InvalidInputError, match="photos"):
        rebind_location_id(original, TARGET_ID)

    assert original.to_dict() == before
    assert all(item.location_id == LOCATION_ID for item in original.reviews)


def test_rebind_rejects_preexisting_unrelated_summary_children():
    original = related_records()[-1]
    original.reviews.append(Review(location_id=TARGET_ID))

    with pytest.raises(InvalidInputError, match="location_id"):
        rebind_location_id(original, TARGET_ID)

    assert original.location_id == LOCATION_ID
    assert original.reviews[0].location_id == LOCATION_ID


def test_rebind_validates_ids_and_does_not_create_replacements(monkeypatch):
    record = related_records()[0]

    def unexpected_generation():
        pytest.fail("Rebinding must not generate IDs")

    monkeypatch.setattr("google_map_crawler.identity.uuid4", unexpected_generation)
    assert rebind_location_id(record, TARGET_ID.upper()).location_id == TARGET_ID.upper()
    with pytest.raises(InvalidLocationIdError):
        rebind_location_id(record, "")
    record.location_id = "invalid"
    with pytest.raises(InvalidLocationIdError):
        rebind_location_id(record, TARGET_ID)


@pytest.mark.parametrize("record", [None, {}, "record"])
def test_rebind_requires_one_of_the_crawler_models(record):
    with pytest.raises(InvalidInputError, match="record"):
        rebind_location_id(record, TARGET_ID)

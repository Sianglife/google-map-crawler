"""Data contracts, isolated containers, timestamps and place associations."""

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest

from google_map_crawler.exceptions import InvalidInputError, InvalidLocationIdError
from google_map_crawler.models import (
    PlaceDetail,
    PlaceSearchResult,
    Review,
    ReviewSummary,
    ReviewTag,
)


LOCATION_ID = "8f2a79bd-b660-4c7e-a9df-f0e9bde31650"
OTHER_ID = "9c01d47f-27be-4bc0-84f7-22df0fbdc291"
MAPS_URL = "https://maps.app.goo.gl/example"
MODEL_CASES = [
    pytest.param(PlaceSearchResult, {"maps_url": MAPS_URL}, id="search"),
    pytest.param(PlaceDetail, {"maps_url": MAPS_URL}, id="detail"),
    pytest.param(ReviewSummary, {}, id="summary"),
    pytest.param(Review, {}, id="review"),
    pytest.param(ReviewTag, {}, id="tag"),
]


@pytest.mark.parametrize("model_type,required", MODEL_CASES)
def test_models_require_an_explicit_id_and_never_generate_their_own(
    model_type, required, monkeypatch
):
    def unexpected_generation():
        pytest.fail("Related models must use the supplied place ID")

    monkeypatch.setattr("google_map_crawler.identity.uuid4", unexpected_generation)

    with pytest.raises(TypeError, match="location_id"):
        model_type(**required)
    with pytest.raises(InvalidLocationIdError):
        model_type(location_id="short-url-token", **required)
    assert model_type(location_id=LOCATION_ID, **required).location_id == LOCATION_ID


@pytest.mark.parametrize("model_type,required", MODEL_CASES)
def test_default_timestamp_is_created_for_each_instance_in_utc(model_type, required):
    before = datetime.now(UTC)
    first = model_type(location_id=LOCATION_ID, **required)
    second = model_type(location_id=LOCATION_ID, **required)
    after = datetime.now(UTC)

    assert before <= first.fetched_at <= second.fetched_at <= after
    assert first.fetched_at.tzinfo is second.fetched_at.tzinfo is UTC
    assert first.fetched_at is not second.fetched_at


@pytest.mark.parametrize("model_type,required", MODEL_CASES)
def test_supplied_time_is_converted_to_utc(model_type, required):
    source = datetime(2026, 11, 23, 14, 30, tzinfo=timezone(timedelta(hours=8)))

    record = model_type(location_id=LOCATION_ID, fetched_at=source, **required)

    assert record.fetched_at == datetime(2026, 11, 23, 6, 30, tzinfo=UTC)
    assert record.fetched_at.tzinfo is UTC
    assert record.to_dict()["fetched_at"] == "2026-11-23T06:30:00+00:00"


@pytest.mark.parametrize("model_type,required", MODEL_CASES)
@pytest.mark.parametrize("invalid", [datetime(2026, 11, 23), None, "2026-11-23"])
def test_naive_or_non_datetime_timestamps_are_rejected(model_type, required, invalid):
    with pytest.raises(InvalidInputError, match="fetched_at"):
        model_type(location_id=LOCATION_ID, fetched_at=invalid, **required)


def test_place_defaults_match_the_spec_and_detail_extends_search_fields():
    search = PlaceSearchResult(location_id=LOCATION_ID, maps_url=MAPS_URL)
    detail = PlaceDetail(location_id=LOCATION_ID, maps_url=MAPS_URL)
    search_data = search.to_dict()
    detail_data = detail.to_dict()

    for data in (search_data, detail_data):
        data.pop("fetched_at")
    assert search_data == {
        "location_id": LOCATION_ID, "maps_url": MAPS_URL,
        "name": None, "category": None, "address": None, "rating": None,
    }
    assert detail_data == {
        **search_data, "price_level": None, "website": None, "phone": None,
        "opening_hours": [], "photos": [],
    }


def test_review_defaults_and_rating_only_reviews_are_valid():
    review = Review(location_id=LOCATION_ID, rating=5)
    tag = ReviewTag(location_id=LOCATION_ID)
    summary = ReviewSummary(location_id=LOCATION_ID, reviews=[review])

    assert review.author is review.author_info is review.content is None
    assert review.photos == []
    assert summary.average_rating is summary.total_count is None
    assert summary.tags == []
    assert summary.reviews == [review]
    assert tag.text is tag.count is None


def test_unknown_counts_and_ratings_are_distinct_from_zero():
    unknown = ReviewSummary(location_id=LOCATION_ID)
    empty = ReviewSummary(location_id=LOCATION_ID, total_count=0, average_rating=0)
    tag = ReviewTag(location_id=LOCATION_ID, count=0)
    place = PlaceDetail(location_id=LOCATION_ID, maps_url=MAPS_URL, rating=0)

    assert unknown.to_dict()["total_count"] is None
    assert empty.to_dict()["total_count"] == 0
    assert empty.average_rating == 0.0
    assert tag.count == 0
    assert place.rating == 0.0


LIST_CASES = [
    pytest.param(PlaceDetail, {"maps_url": MAPS_URL}, "photos", "photo-url", id="place-photos"),
    pytest.param(PlaceDetail, {"maps_url": MAPS_URL}, "opening_hours", "星期一休息", id="hours"),
    pytest.param(Review, {}, "photos", "review-photo-url", id="review-photos"),
    pytest.param(ReviewSummary, {}, "reviews", Review(location_id=LOCATION_ID), id="reviews"),
    pytest.param(ReviewSummary, {}, "tags", ReviewTag(location_id=LOCATION_ID), id="tags"),
]


@pytest.mark.parametrize("model_type,required,name,item", LIST_CASES)
def test_default_lists_are_independent(model_type, required, name, item):
    first = model_type(location_id=LOCATION_ID, **required)
    second = model_type(location_id=LOCATION_ID, **required)

    getattr(first, name).append(item)

    assert getattr(second, name) == []


@pytest.mark.parametrize("model_type,required,name,item", LIST_CASES)
def test_explicit_lists_do_not_share_the_callers_container(model_type, required, name, item):
    source = [item]
    first = model_type(location_id=LOCATION_ID, **required, **{name: source})
    second = model_type(location_id=LOCATION_ID, **required, **{name: source})

    source.clear()
    getattr(first, name).clear()

    assert getattr(second, name) == [item]


@pytest.mark.parametrize("model_type", [PlaceSearchResult, PlaceDetail])
@pytest.mark.parametrize("invalid", [-0.1, 5.1, 4.25, float("nan"), float("inf"), "4.5", True])
def test_place_rating_rejects_invalid_values_or_precision(model_type, invalid):
    with pytest.raises(InvalidInputError, match="rating"):
        model_type(location_id=LOCATION_ID, maps_url=MAPS_URL, rating=invalid)


@pytest.mark.parametrize("invalid", [None, "", "  ", 42])
def test_place_requires_a_non_empty_maps_url(invalid):
    with pytest.raises(InvalidInputError, match="maps_url"):
        PlaceDetail(location_id=LOCATION_ID, maps_url=invalid)


@pytest.mark.parametrize(
    "model_type,required,name,value",
    [
        (PlaceSearchResult, {"maps_url": MAPS_URL}, "name", 12),
        (PlaceDetail, {"maps_url": MAPS_URL}, "phone", 1234),
        (PlaceDetail, {"maps_url": MAPS_URL}, "photos", None),
        (PlaceDetail, {"maps_url": MAPS_URL}, "opening_hours", [None]),
        (Review, {}, "author_info", 12),
        (Review, {}, "photos", ("photo",)),
        (Review, {}, "rating", 4.5),
        (Review, {}, "rating", True),
        (ReviewTag, {}, "text", 12),
        (ReviewTag, {}, "count", -1),
        (ReviewTag, {}, "count", True),
        (ReviewSummary, {}, "average_rating", float("nan")),
        (ReviewSummary, {}, "total_count", -1),
        (ReviewSummary, {}, "total_count", False),
        (ReviewSummary, {}, "reviews", [{"rating": 5}]),
        (ReviewSummary, {}, "tags", ["美食"]),
    ],
)
def test_wrong_field_types_and_counts_report_the_field(model_type, required, name, value):
    with pytest.raises(InvalidInputError, match=name):
        model_type(location_id=LOCATION_ID, **required, **{name: value})


@pytest.mark.parametrize("name,child_type", [("reviews", Review), ("tags", ReviewTag)])
def test_summary_rejects_different_place_ids_without_rewriting_children(name, child_type):
    child = child_type(location_id=OTHER_ID)

    with pytest.raises(InvalidInputError, match=name):
        ReviewSummary(location_id=LOCATION_ID, **{name: [child]})

    assert child.location_id == OTHER_ID


def test_to_dict_preserves_nested_data_and_returns_detached_json_compatible_values():
    when = datetime(2026, 11, 23, 6, 30, tzinfo=UTC)
    review = Review(
        location_id=LOCATION_ID, fetched_at=when, rating=5,
        content="  餐點好吃！  ", photos=["photo-2", "photo-1"],
    )
    tag = ReviewTag(location_id=LOCATION_ID, fetched_at=when, text="美食", count=0)
    summary = ReviewSummary(
        location_id=LOCATION_ID, fetched_at=when, total_count=100,
        average_rating=4.25, reviews=[review], tags=[tag],
    )

    data = json.loads(json.dumps(summary.to_dict(), ensure_ascii=False, allow_nan=False))

    assert data["total_count"] == 100
    assert len(data["reviews"]) == 1
    assert data["reviews"][0]["location_id"] == data["tags"][0]["location_id"] == LOCATION_ID
    assert data["reviews"][0]["content"] == "  餐點好吃！  "
    assert data["reviews"][0]["author"] is None
    assert data["reviews"][0]["fetched_at"] == "2026-11-23T06:30:00+00:00"
    assert data["reviews"][0]["photos"] == ["photo-2", "photo-1"]

    detached = summary.to_dict()
    detached["reviews"][0]["photos"].append("new-photo")
    detached["tags"][0]["text"] = "changed"

    assert review.photos == ["photo-2", "photo-1"]
    assert tag.text == "美食"
    assert isinstance(summary.fetched_at, datetime)


def test_place_text_is_preserved_without_normalization():
    detail = PlaceDetail(
        location_id=LOCATION_ID, maps_url=MAPS_URL, name=" 臺北店 ",
        address="臺北市 1號 2樓", price_level="200–400 元",
        opening_hours=["星期一休息", "星期二 09:00–17:00"],
    )

    assert detail.to_dict()["name"] == " 臺北店 "
    assert detail.address == "臺北市 1號 2樓"
    assert detail.price_level == "200–400 元"
    assert detail.opening_hours == ["星期一休息", "星期二 09:00–17:00"]

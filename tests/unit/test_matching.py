"""Directional comparison, sparse history and complete candidate selection."""

from dataclasses import FrozenInstanceError, replace
from itertools import permutations
from types import MappingProxyType

import pytest

from google_map_crawler.exceptions import (
    AmbiguousPlaceMatchError,
    InvalidInputError,
    InvalidLocationIdError,
)
from google_map_crawler.matching import compare_places, find_place_match
from google_map_crawler.models import PlaceDetail, PlaceSearchResult


NEW_ID = "8f2a79bd-b660-4c7e-a9df-f0e9bde31650"
OLD_IDS = (
    "9c01d47f-27be-4bc0-84f7-22df0fbdc291",
    "6b7db9d9-2014-4d7a-8075-4e5a820e1dab",
    "c145620a-49a7-4bc1-8389-7506c54f92ad",
)
CHANGED_FIELDS = ("name", "address", "website", "phone")


def incoming_place():
    return PlaceDetail(
        location_id=NEW_ID, maps_url="https://maps.app.goo.gl/current",
        name="測試地點", category="餐廳", address="臺北市一號",
        rating=4.5, price_level="200–400 元", website="https://example.com",
        phone="02-12345678", opening_hours=["星期一休息", "星期二營業"],
        photos=["photo-1", "photo-2"],
    )


def existing_record(incoming, count=0, location_id=OLD_IDS[0]):
    record = incoming.to_dict()
    record["location_id"] = location_id
    for name in CHANGED_FIELDS[:count]:
        record[name] = f"previous-{name}"
    return record


@pytest.mark.parametrize("count", [0, 1, 2, 3, 4])
def test_two_field_threshold_reports_all_differences(count):
    incoming = incoming_place()
    result = compare_places(existing_record(incoming, count), incoming)

    assert result.existing_location_id == OLD_IDS[0]
    assert result.difference_count == count
    assert result.different_fields == CHANGED_FIELDS[:count]
    assert result.is_match is (count <= 2)
    assert result.compared_fields == (
        "maps_url", "name", "category", "address", "rating", "price_level",
        "website", "phone", "opening_hours", "photos",
    )


@pytest.mark.parametrize("value", [None, "", " \t\n", []])
def test_empty_existing_fields_are_not_a_baseline(value):
    result = compare_places({"location_id": OLD_IDS[0], "phone": value}, incoming_place())

    assert result.compared_fields == result.different_fields == ()
    assert result.is_match


def test_missing_fields_are_not_filled_and_sparse_history_still_matches():
    history = {"location_id": OLD_IDS[0]}
    before = dict(history)

    result = compare_places(MappingProxyType(history), incoming_place())

    assert result.compared_fields == ()
    assert result.difference_count == 0
    assert result.is_match
    assert history == before


def test_numeric_zero_is_compared_instead_of_treated_as_empty():
    incoming = replace(incoming_place(), rating=None)

    result = compare_places({"location_id": OLD_IDS[0], "rating": 0}, incoming)

    assert result.compared_fields == result.different_fields == ("rating",)


@pytest.mark.parametrize("name,empty", [("phone", None), ("name", ""), ("photos", [])])
def test_incoming_empty_values_count_against_existing_data(name, empty):
    incoming = incoming_place()
    history = existing_record(incoming)

    result = compare_places(history, replace(incoming, **{name: empty}))

    assert result.different_fields == (name,)


def test_added_data_only_becomes_a_baseline_after_the_caller_saves_it():
    incoming = incoming_place()
    history = {"location_id": OLD_IDS[0], "maps_url": incoming.maps_url}
    assert compare_places(history, incoming).difference_count == 0

    history["phone"] = incoming.phone
    result = compare_places(history, replace(incoming, phone="new-phone"))

    assert result.different_fields == ("phone",)


def test_comparison_is_directional_and_metadata_does_not_affect_it():
    incoming = incoming_place()
    older = PlaceDetail(location_id=OLD_IDS[0], maps_url=incoming.maps_url)

    assert compare_places(older, incoming).difference_count == 0
    assert compare_places(incoming, older).difference_count > 2
    history = existing_record(incoming)
    history.update({"fetched_at": "unparsed-old-time", "_id": object(), "status": False})
    assert compare_places(history, incoming).difference_count == 0


def test_url_rating_and_photo_changes_each_count_once_even_with_the_same_id():
    incoming = incoming_place()
    history = existing_record(incoming, location_id=NEW_ID)
    history.update(maps_url="https://maps.app.goo.gl/previous", rating=4.0, photos=["old"])

    result = compare_places(history, incoming)

    assert result.different_fields == ("maps_url", "rating", "photos")
    assert not result.is_match


@pytest.mark.parametrize("name", ["opening_hours", "photos"])
def test_list_order_or_multiple_changed_items_is_one_difference(name):
    incoming = incoming_place()
    history = existing_record(incoming)
    history[name] = list(reversed(history[name]))

    assert compare_places(history, incoming).different_fields == (name,)
    history[name] = ["different-1", "different-2", "different-3"]
    assert compare_places(history, incoming).difference_count == 1


def test_result_is_immutable_and_independent_of_later_input_changes():
    incoming = incoming_place()
    history = existing_record(incoming, 1)
    result = compare_places(history, incoming)
    incoming.name = "changed-later"
    history["photos"].clear()

    assert result.different_fields == ("name",)
    with pytest.raises(FrozenInstanceError):
        result.different_fields = ()


@pytest.mark.parametrize(
    "counts,expected_index",
    [([0, 1, 2], 0), ([1, 2], 0), ([2, 1, 0], 2), ([1, 1, 0], 2),
     ([3, 2], 1), ([3, 4], None), ([], None)],
)
def test_find_match_chooses_only_the_unique_fewest_qualifying_differences(counts, expected_index):
    incoming = incoming_place()
    candidates = [existing_record(incoming, count, OLD_IDS[i]) for i, count in enumerate(counts)]

    result = find_place_match(incoming, candidates)

    if expected_index is None:
        assert result is None
    else:
        assert result.existing_location_id == OLD_IDS[expected_index]
        assert result.difference_count == counts[expected_index]
    assert incoming.location_id == NEW_ID


@pytest.mark.parametrize("counts", [(1, 1, 2), (0, 0, 1), (2, 2, 3)])
def test_only_tied_best_candidates_are_attached_to_the_ambiguity_error(counts):
    incoming = incoming_place()
    candidates = [existing_record(incoming, count, OLD_IDS[i]) for i, count in enumerate(counts)]

    with pytest.raises(AmbiguousPlaceMatchError) as caught:
        find_place_match(incoming, candidates)

    assert isinstance(caught.value.matches, tuple)
    assert tuple(item.existing_location_id for item in caught.value.matches) == OLD_IDS[:2]
    assert all(item.difference_count == counts[0] for item in caught.value.matches)
    assert incoming.location_id == NEW_ID


def test_selection_is_independent_of_candidate_order():
    incoming = incoming_place()
    candidates = [existing_record(incoming, count, OLD_IDS[i]) for i, count in enumerate((2, 0, 1))]

    for ordering in permutations(candidates):
        assert find_place_match(incoming, ordering).existing_location_id == OLD_IDS[1]


def test_generator_is_fully_consumed_even_after_an_exact_match():
    incoming = incoming_place()
    visited = []

    def candidates():
        for index, count in enumerate((0, 1, 0)):
            visited.append(index)
            yield existing_record(incoming, count, OLD_IDS[index])

    with pytest.raises(AmbiguousPlaceMatchError):
        find_place_match(incoming, candidates())
    assert visited == [0, 1, 2]


def test_repeated_best_candidate_is_not_silently_deduplicated():
    incoming = incoming_place()
    history = existing_record(incoming)

    with pytest.raises(AmbiguousPlaceMatchError) as caught:
        find_place_match(incoming, [history, history])

    assert len(caught.value.matches) == 2


def test_invalid_later_candidate_is_not_hidden_by_an_earlier_match():
    incoming = incoming_place()
    invalid = existing_record(incoming)
    invalid["phone"] = 12345

    with pytest.raises(InvalidInputError, match="existing.phone"):
        find_place_match(incoming, [existing_record(incoming), invalid])


def test_incoming_data_is_snapshotted_before_consuming_candidates():
    incoming = incoming_place()
    first = existing_record(incoming, location_id=OLD_IDS[0])
    second = existing_record(incoming, location_id=OLD_IDS[1])

    def candidates():
        yield first
        incoming.name = "changed-by-the-caller"
        yield second

    with pytest.raises(AmbiguousPlaceMatchError) as caught:
        find_place_match(incoming, candidates())

    assert all(item.difference_count == 0 for item in caught.value.matches)


@pytest.mark.parametrize("incoming", [None, {}, PlaceSearchResult(location_id=NEW_ID, maps_url="url")])
def test_incoming_must_be_a_detail_even_when_no_candidates_are_supplied(incoming):
    with pytest.raises(InvalidInputError, match="incoming"):
        find_place_match(incoming, [])


@pytest.mark.parametrize("invalid", [None, "record", 42, PlaceSearchResult(location_id=NEW_ID, maps_url="url")])
def test_existing_requires_a_detail_or_mapping(invalid):
    with pytest.raises(InvalidInputError, match="existing"):
        compare_places(invalid, incoming_place())


@pytest.mark.parametrize("invalid", [None, "", [], "not-a-uuid"])
def test_existing_requires_a_valid_internal_id(invalid):
    with pytest.raises(InvalidLocationIdError):
        compare_places({"location_id": invalid}, incoming_place())


@pytest.mark.parametrize(
    "name,value",
    [("name", 42), ("phone", 123), ("photos", ("photo",)), ("photos", [None]),
     ("opening_hours", {}), ("rating", True), ("rating", float("nan")),
     ("rating", float("inf")), ("rating", 4.25), ("rating", 6), ("rating", -1)],
)
def test_non_empty_history_values_are_validated_without_coercion(name, value):
    with pytest.raises(InvalidInputError, match=f"existing.{name}"):
        compare_places({"location_id": OLD_IDS[0], name: value}, incoming_place())


@pytest.mark.parametrize("invalid", [None, 42, "", {}, b"records"])
def test_candidates_must_be_an_iterable_of_records(invalid):
    with pytest.raises(InvalidInputError, match="candidates"):
        find_place_match(incoming_place(), invalid)


def test_matching_does_not_generate_ids_or_modify_records(monkeypatch):
    incoming = incoming_place()
    history = existing_record(incoming, 1)
    before = incoming.to_dict()
    original_history = dict(history)

    def unexpected_generation():
        pytest.fail("Matching must preserve existing IDs")

    monkeypatch.setattr("google_map_crawler.identity.uuid4", unexpected_generation)
    find_place_match(incoming, [history])
    find_place_match(incoming, [])

    assert incoming.to_dict() == before
    assert history == original_history


def test_non_empty_text_is_compared_without_normalization():
    incoming = incoming_place()
    history = existing_record(incoming)
    history["name"] = f" {incoming.name} "
    history["address"] = incoming.address.replace("臺", "台")

    assert compare_places(history, incoming).different_fields == ("name", "address")


def test_ambiguity_error_preserves_manual_message_usage():
    error = AmbiguousPlaceMatchError("caller supplied message")

    assert str(error) == "caller supplied message"
    assert error.matches == ()

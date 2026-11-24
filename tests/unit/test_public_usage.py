"""Exercise documented imports and the offline example as an installed user."""

import json
from pathlib import Path
import subprocess
import sys
from uuid import UUID

import pytest

from google_map_crawler import (
    AmbiguousPlaceMatchError,
    CrawlerError,
    InvalidInputError,
    PlaceDetail,
    PlaceSearchResult,
    Review,
    ReviewSummary,
    ReviewTag,
    compare_places,
    create_location_id,
    find_place_match,
    rebind_location_id,
    resolve_location_id,
    validate_count,
    validate_location_id,
    validate_non_empty_string,
)


def test_public_tools_and_models_can_be_used_together():
    location_id = create_location_id()
    found = PlaceSearchResult(
        location_id=location_id, maps_url="https://maps.app.goo.gl/example"
    )
    detail = PlaceDetail(
        location_id=resolve_location_id(found.location_id), maps_url=found.maps_url
    )
    review = Review(location_id=detail.location_id, rating=5)
    tag = ReviewTag(location_id=detail.location_id, text="餐點", count=1)
    summary = ReviewSummary(location_id=detail.location_id, reviews=[review], tags=[tag])

    assert validate_location_id(summary.location_id) == found.location_id
    assert validate_count(0, name="max_places") == 0
    assert validate_non_empty_string("搜尋", name="keyword") == "搜尋"
    with pytest.raises(CrawlerError) as caught:
        validate_count(-1, name="max_places")
    assert isinstance(caught.value, InvalidInputError)


def test_example_runs_from_another_directory_without_creating_output_files(tmp_path):
    example = Path(__file__).resolve().parents[2] / "examples" / "create_models.py"
    result = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", str(example)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=30,
    )
    data = json.loads(result.stdout)

    location_id = data["place"]["location_id"]
    summary = data["review_summary"]
    assert UUID(location_id).version == 4
    assert summary["location_id"] == summary["reviews"][0]["location_id"] == location_id
    assert summary["tags"][0]["location_id"] == location_id
    assert summary["reviews"][0]["rating"] == 5
    assert summary["reviews"][0]["content"] is None
    assert summary["total_count"] == 100
    assert len(summary["reviews"]) == 1
    assert list(tmp_path.iterdir()) == []


def test_public_matching_and_id_adoption_do_not_change_incoming_data():
    location_id = create_location_id()
    incoming = PlaceDetail(location_id=location_id, maps_url="url", name="地點")
    history_id = create_location_id()
    history = {"location_id": history_id, "maps_url": "url", "name": "地點"}

    assert compare_places(history, incoming).difference_count == 0
    match = find_place_match(incoming, [history])
    adopted = rebind_location_id(incoming, match.existing_location_id)

    assert adopted.location_id == history_id
    assert incoming.location_id == location_id
    with pytest.raises(AmbiguousPlaceMatchError) as caught:
        find_place_match(incoming, [history, history])
    assert len(caught.value.matches) == 2


def test_matching_example_demonstrates_selection_no_match_and_ties(tmp_path):
    example = Path(__file__).resolve().parents[2] / "examples" / "match_places.py"
    result = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", str(example)],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", check=True, timeout=30,
    )
    data = json.loads(result.stdout)

    chosen_id = data["best_match"]["existing_location_id"]
    assert data["best_match"]["difference_count"] == 1
    assert data["best_match"]["different_fields"] == ["phone"]
    assert data["adopted_place"]["location_id"] == chosen_id
    summary = data["adopted_summary"]
    assert summary["location_id"] == summary["reviews"][0]["location_id"] == chosen_id
    assert summary["tags"][0]["location_id"] == chosen_id
    assert data["no_match"] == {"result": None, "kept_location_id": data["original_location_id"]}
    assert data["ambiguity"]["error"] == "AmbiguousPlaceMatchError"
    assert len(data["ambiguity"]["matches"]) == 2
    assert all(item["difference_count"] == 1 for item in data["ambiguity"]["matches"])
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("arguments,code", [([], 0), (["https://example.com/maps/place/a"], 2)])
def test_url_example_full_and_invalid_paths_are_offline(tmp_path, arguments, code):
    example = Path(__file__).resolve().parents[2] / "examples" / "expand_url.py"
    result = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", str(example), *arguments],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == code
    if code == 0:
        assert result.stdout.strip() == "https://www.google.com/maps/search/?api=1&query=Taipei%20101"
        assert result.stderr == ""
    else:
        assert result.stdout == "" and "InvalidMapsUrlError" in result.stderr
    assert list(tmp_path.iterdir()) == []

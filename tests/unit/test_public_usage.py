"""Exercise documented imports and the offline example as an installed user."""

import json
from pathlib import Path
import subprocess
import sys
from uuid import UUID

import pytest

from google_map_crawler import (
    CrawlerError,
    InvalidInputError,
    PlaceDetail,
    PlaceSearchResult,
    Review,
    ReviewSummary,
    ReviewTag,
    create_location_id,
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

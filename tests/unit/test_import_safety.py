"""Verify that the installed package can be imported without external effects."""

import subprocess
import sys


def test_import_from_another_directory_has_no_external_side_effects(tmp_path):
    script = """
import sys

def prevent_external_effects(event, args):
    if event.startswith("socket.") or event in {
        "subprocess.Popen",
        "os.system",
        "os.posix_spawn",
        "os.exec",
        "os.spawn",
        "os.startfile",
        "os.startfile/2",
    }:
        raise AssertionError(f"Package import attempted an external effect: {event}")

sys.addaudithook(prevent_external_effects)

import google_map_crawler
from google_map_crawler.browser import BrowserConfig, BrowserSession
from google_map_crawler.interaction import click_with_retry, retry_operation, wait_for_element, wait_until

config = BrowserConfig()
session = BrowserSession(config)
assert "selenium" not in sys.modules
session.close()

for call in (
    lambda: wait_for_element(None, ("id", "example"), timeout=0),
    lambda: wait_until(None, None),
    lambda: retry_operation(None),
    lambda: retry_operation(lambda seconds: True, max_retries=4),
    lambda: click_with_retry(None, ("id", "example"), is_complete=None),
):
    try:
        call()
    except google_map_crawler.InvalidInputError:
        pass
    else:
        raise AssertionError("Invalid wait arguments were accepted")
assert "selenium" not in sys.modules

assert retry_operation(lambda seconds: 0) == 0
assert "selenium" not in sys.modules

full_url = "https://www.google.com/maps/place/Example/@25,121,17z"
assert google_map_crawler.expand_short_url(full_url) == full_url
try:
    google_map_crawler.expand_short_url("https://example.com/maps/place/a")
except google_map_crawler.InvalidMapsUrlError:
    pass
else:
    raise AssertionError("Invalid Maps URL was accepted")
assert "selenium" not in sys.modules

location_id = google_map_crawler.resolve_location_id()
place = google_map_crawler.PlaceDetail(
    location_id=location_id, maps_url="https://maps.app.goo.gl/example"
)
review = google_map_crawler.Review(location_id=location_id, rating=5)
summary = google_map_crawler.ReviewSummary(location_id=location_id, reviews=[review])
assert place.to_dict()["location_id"] == summary.to_dict()["location_id"]

existing_id = google_map_crawler.create_location_id()
existing = {"location_id": existing_id, "maps_url": place.maps_url}
assert google_map_crawler.compare_places(existing, place).is_match
match = google_map_crawler.find_place_match(place, [existing])
adopted = google_map_crawler.rebind_location_id(summary, match.existing_location_id)
assert adopted.reviews[0].location_id == existing_id
assert summary.reviews[0].location_id == location_id

print(google_map_crawler.__name__)
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )

    assert result.stdout.strip() == "google_map_crawler"

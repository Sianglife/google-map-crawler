"""Verify that the installed package can be imported without external effects."""

import subprocess
import sys


def test_import_from_another_directory_has_no_external_side_effects(tmp_path):
    script = """
import sys

def prevent_external_effects(event, args):
    if event in {
        "socket.__new__",
        "socket.connect",
        "socket.getaddrinfo",
        "subprocess.Popen",
        "os.system",
        "os.posix_spawn",
        "os.exec",
        "os.spawn",
    }:
        raise AssertionError(f"Package import attempted an external effect: {event}")

sys.addaudithook(prevent_external_effects)

import google_map_crawler

location_id = google_map_crawler.resolve_location_id()
place = google_map_crawler.PlaceDetail(
    location_id=location_id, maps_url="https://maps.app.goo.gl/example"
)
review = google_map_crawler.Review(location_id=location_id, rating=5)
summary = google_map_crawler.ReviewSummary(location_id=location_id, reviews=[review])
assert place.to_dict()["location_id"] == summary.to_dict()["location_id"]

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

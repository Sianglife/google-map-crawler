"""Illustrate matching and explicit ID adoption with local, fictional data."""

from dataclasses import replace
import json

from google_map_crawler import (
    AmbiguousPlaceMatchError,
    PlaceDetail,
    Review,
    ReviewSummary,
    ReviewTag,
    find_place_match,
    rebind_location_id,
    resolve_location_id,
)


def build_example() -> dict:
    incoming = PlaceDetail(
        location_id=resolve_location_id(),
        maps_url="https://www.google.com/maps/search/?api=1&query=範例地點",
        name="離線範例地點", phone="02-12345678", address="範例路一號",
    )
    closest = replace(incoming, location_id=resolve_location_id(), phone="old-phone")
    other = replace(closest, location_id=resolve_location_id(), address="previous-address")

    # Both qualify, but only the one-difference candidate should be selected.
    match = find_place_match(incoming, [other, closest])
    adopted = rebind_location_id(incoming, match.existing_location_id)
    summary = ReviewSummary(
        location_id=incoming.location_id,
        reviews=[Review(location_id=incoming.location_id, rating=5)],
        tags=[ReviewTag(location_id=incoming.location_id, text="餐點", count=1)],
    )
    adopted_summary = rebind_location_id(summary, match.existing_location_id)

    no_match = find_place_match(
        incoming,
        [replace(other, name="different-name", website="https://example.com/old")],
    )
    kept = incoming if no_match is None else rebind_location_id(incoming, no_match.existing_location_id)

    tied = replace(closest, location_id=resolve_location_id())
    try:
        find_place_match(incoming, [closest, tied, other])
    except AmbiguousPlaceMatchError as error:
        ambiguity = {
            "error": type(error).__name__,
            "matches": [
                {"location_id": item.existing_location_id,
                 "difference_count": item.difference_count,
                 "different_fields": list(item.different_fields)}
                for item in error.matches
            ],
        }

    return {
        "original_location_id": incoming.location_id,
        "best_match": {
            "existing_location_id": match.existing_location_id,
            "difference_count": match.difference_count,
            "different_fields": list(match.different_fields),
        },
        "adopted_place": adopted.to_dict(),
        "adopted_summary": adopted_summary.to_dict(),
        "no_match": {"result": no_match, "kept_location_id": kept.location_id},
        "ambiguity": ambiguity,
    }


if __name__ == "__main__":
    print(json.dumps(build_example(), ensure_ascii=False, indent=2))

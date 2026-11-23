"""Create illustrative data locally; this example does not fetch real places."""

import json

from google_map_crawler import (
    PlaceDetail,
    Review,
    ReviewSummary,
    ReviewTag,
    resolve_location_id,
)


def build_example() -> dict:
    """Return related place/review data using a single internal place ID."""
    location_id = resolve_location_id()
    place = PlaceDetail(
        location_id=location_id,
        maps_url="https://www.google.com/maps/search/?api=1&query=範例地點",
        name="離線範例地點",
        rating=4.5,
        price_level="200–400 元",
        opening_hours=["星期一休息", "星期二 09:00–17:00"],
    )
    review = Review(location_id=location_id, rating=5)
    tag = ReviewTag(location_id=location_id, text="餐點", count=3)
    summary = ReviewSummary(
        location_id=location_id,
        average_rating=4.5,
        total_count=100,
        reviews=[review],
        tags=[tag],
    )
    return {"place": place.to_dict(), "review_summary": summary.to_dict()}


if __name__ == "__main__":
    print(json.dumps(build_example(), ensure_ascii=False, indent=2))

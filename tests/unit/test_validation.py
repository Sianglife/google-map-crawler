"""Boundary validation before any browser work can begin."""

import pytest

from google_map_crawler.exceptions import InvalidInputError
from google_map_crawler.validation import validate_count, validate_non_empty_string


@pytest.mark.parametrize("value", [0, 1, 20, 50, 100])
def test_count_accepts_zero_and_positive_integers(value):
    assert validate_count(value, name="max_places") == value


@pytest.mark.parametrize("value", [-1, True, False, 1.0, "20", None])
def test_invalid_count_reports_the_parameter_name(value):
    with pytest.raises(InvalidInputError, match="max_photos"):
        validate_count(value, name="max_photos")


@pytest.mark.parametrize("value", ["", " \t\n", None, 12])
def test_required_text_rejects_missing_or_whitespace_values(value):
    with pytest.raises(InvalidInputError, match="keyword"):
        validate_non_empty_string(value, name="keyword")


def test_required_text_is_not_normalized():
    original = "  臺北 寺廟  "

    assert validate_non_empty_string(original, name="keyword") == original

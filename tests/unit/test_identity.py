"""Contracts for generating new IDs and preserving existing place identity."""

from uuid import UUID

import pytest

from google_map_crawler.exceptions import InvalidInputError, InvalidLocationIdError
from google_map_crawler.identity import (
    create_location_id,
    resolve_location_id,
    validate_location_id,
)


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

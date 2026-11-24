"""Argument validation that does not require browser or network access."""

from math import isfinite

from .exceptions import InvalidInputError


def validate_positive_timeout(value: float, *, name: str) -> float:
    """Accept a finite positive duration, rejecting booleans and numeric strings."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidInputError(f"{name} must be a finite positive number")
    try:
        result = float(value)
    except OverflowError as error:
        raise InvalidInputError(f"{name} must be a finite positive number") from error
    if not isfinite(result) or result <= 0:
        raise InvalidInputError(f"{name} must be a finite positive number")
    return result


def validate_count(value: int, *, name: str) -> int:
    """Accept a non-negative integer, excluding bool despite its int ancestry."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidInputError(f"{name} must be a non-negative integer")
    return value


def validate_non_empty_string(value: str, *, name: str) -> str:
    """Require non-whitespace text, preserving the original string on success."""
    if not isinstance(value, str) or not value.strip():
        raise InvalidInputError(f"{name} must be a non-empty string")
    return value

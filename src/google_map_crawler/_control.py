"""Prevent nested operation controllers from multiplying retries and waits."""

from contextlib import contextmanager
from contextvars import ContextVar

from .exceptions import InvalidInputError


_ACTIVE = ContextVar("google_map_crawler_control", default=())


@contextmanager
def control_scope(kind: str):
    active = _ACTIVE.get()
    if (kind == "wait" and "wait" in active) or (kind != "wait" and active):
        raise InvalidInputError(
            f"Cannot nest {kind} inside {'/'.join(active)}; use one operation controller"
        )
    token = _ACTIVE.set((*active, kind))
    try:
        yield
    finally:
        _ACTIVE.reset(token)

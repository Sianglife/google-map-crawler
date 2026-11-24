"""Bounded replay, recovery budgets, guarded clicks and controller ownership."""

import errno
import ssl
from types import SimpleNamespace
from urllib.error import URLError

import pytest
from selenium.common.exceptions import (
    ElementClickInterceptedException, ElementNotInteractableException,
    InvalidSelectorException, InvalidSessionIdException, NoSuchElementException,
    StaleElementReferenceException, TimeoutException, WebDriverException,
)
from selenium.webdriver.support import wait as selenium_wait

from google_map_crawler import (
    InvalidInputError, OperationRetryError, OperationRetryTimeoutError,
    PageAccessBlockedError, PageLoadTimeoutError, PageWaitError, ParseError,
    PlaceNotFoundError, UrlExpansionError, expand_short_url,
)
from google_map_crawler import interaction, urls
from google_map_crawler.interaction import click_with_retry, retry_operation, wait_until


@pytest.fixture
def clock(monkeypatch):
    class Clock:
        now = 0.0

        def monotonic(self):
            return self.now

        def sleep(self, seconds):
            self.now += seconds

    clock = Clock()
    monkeypatch.setattr(interaction, "monotonic", clock.monotonic)
    monkeypatch.setattr(selenium_wait, "time", clock)
    return clock


@pytest.mark.parametrize("max_retries", [0, 1, 2, 3])
def test_recoverable_failure_has_a_finite_attempt_limit(max_retries, clock):
    errors = []
    recoveries = []

    def action(seconds):
        error = StaleElementReferenceException("replaced")
        errors.append(error)
        raise error

    with pytest.raises(OperationRetryError) as failure:
        retry_operation(action, max_retries=max_retries, operation="read", locator=("id", "x"),
                        recover=lambda error, seconds: recoveries.append(error))
    error = failure.value
    assert error.reason == "attempts_exhausted"
    assert error.operation == "read" and error.locator == ("id", "x")
    assert error.attempts == len(errors) == max_retries + 1
    assert len(recoveries) == max_retries
    assert error.last_error is error.__cause__ is errors[-1]


@pytest.mark.parametrize("result", [None, False, 0, [], {}, ["record"]])
def test_success_returns_original_value_including_falsy_results(result, clock):
    calls = []
    assert retry_operation(lambda seconds: calls.append(seconds) or result) is result
    assert calls == [30]


@pytest.mark.parametrize("original", [
    InvalidInputError("bad input"), PlaceNotFoundError("gone"), ParseError("bad data"),
    PageAccessBlockedError("verify"), UrlExpansionError("URL has its own retry policy"),
    PageLoadTimeoutError("already waited"), InvalidSelectorException("bad CSS"),
    InvalidSessionIdException("closed"), NoSuchElementException("use a wait"),
    WebDriverException("unknown"), TimeoutException("unknown browser outcome"),
    RuntimeError("bug"), ValueError("bug"), URLError(ssl.SSLCertVerificationError("certificate")),
])
def test_permanent_or_unknown_failure_is_not_retried(original, clock):
    calls = []

    def action(seconds):
        calls.append(seconds)
        raise original

    with pytest.raises(type(original)) as failure:
        retry_operation(action)
    assert failure.value is original and len(calls) == 1


@pytest.mark.parametrize("original", [
    ElementClickInterceptedException("overlay"), ElementNotInteractableException("hidden"),
    URLError(ConnectionResetError(errno.ECONNRESET, "reset")), TimeoutError("socket timeout"),
])
def test_known_transient_failure_can_recover(original, clock):
    calls = []

    def action(seconds):
        calls.append(seconds)
        if len(calls) == 1:
            raise original
        return "ready"

    assert retry_operation(action) == "ready" and len(calls) == 2


def test_wrapped_stale_can_retry_but_wait_timeout_cannot(clock):
    wrapped = PageWaitError("stale read")
    wrapped.__cause__ = StaleElementReferenceException("replaced")
    calls = []

    def action(seconds):
        calls.append(seconds)
        if len(calls) == 1:
            raise wrapped
        return 42

    assert retry_operation(action) == 42 and len(calls) == 2


def test_attempts_and_recovery_share_remaining_time(clock):
    observed = []

    def action(seconds):
        observed.append(seconds)
        clock.now += 2
        if len(observed) == 1:
            raise StaleElementReferenceException("replaced")
        return "ready"

    def recover(error, seconds):
        observed.append(seconds)
        clock.now += 1

    assert retry_operation(action, timeout=10, recover=recover) == "ready"
    assert observed == [10, 8, 7]


def test_late_success_is_not_returned(clock):
    def action(seconds):
        clock.now += seconds
        return "late"

    with pytest.raises(OperationRetryTimeoutError) as failure:
        retry_operation(action, timeout=1)
    assert failure.value.attempts == 1 and failure.value.reason == "timeout"


def test_recovery_expiry_does_not_start_another_action(clock):
    original = StaleElementReferenceException("replaced")
    calls = []

    def action(seconds):
        calls.append(seconds)
        raise original

    def recover(error, seconds):
        clock.now += seconds

    with pytest.raises(OperationRetryTimeoutError) as failure:
        retry_operation(action, recover=recover)
    assert len(calls) == 1 and failure.value.last_error is original


def test_failed_recovery_preserves_both_errors(clock):
    original, recovery_error = StaleElementReferenceException("replaced"), ParseError("bad recovery")

    def action(seconds):
        raise original

    def recover(error, seconds):
        raise recovery_error

    with pytest.raises(OperationRetryError) as failure:
        retry_operation(action, recover=recover)
    assert failure.value.reason == "recovery_failed"
    assert failure.value.last_error is original and failure.value.__cause__ is recovery_error


class Driver:
    def __init__(self, click):
        self.timeouts = SimpleNamespace(implicit_wait=0)
        self.click_action = click
        self.complete = False
        self.finds = self.clicks = 0

    def find_element(self, by, value):
        self.finds += 1
        return self

    def is_displayed(self):
        return True

    def is_enabled(self):
        return True

    def click(self):
        self.clicks += 1
        self.click_action(self)


def test_click_rechecks_state_and_relocates_after_rejected_click(clock):
    def click(driver):
        if driver.clicks == 1:
            raise StaleElementReferenceException("replaced")
        driver.complete = True

    driver = Driver(click)
    assert click_with_retry(driver, ("id", "button"), is_complete=lambda d: d.complete)
    assert driver.finds == driver.clicks == 2


def test_already_completed_click_is_not_replayed(clock):
    driver = Driver(lambda d: None)
    driver.complete = True
    assert click_with_retry(driver, ("id", "button"), is_complete=lambda d: d.complete)
    assert driver.finds == driver.clicks == 0


def test_lost_click_acknowledgement_is_verified_without_replay(clock):
    def click(driver):
        driver.complete = True
        raise TimeoutException("acknowledgement lost")

    driver = Driver(click)
    assert click_with_retry(driver, ("id", "button"), is_complete=lambda d: d.complete)
    assert driver.clicks == 1


@pytest.mark.parametrize("original", [
    TimeoutException("unknown"), URLError(ConnectionResetError(errno.ECONNRESET, "unknown")),
])
def test_unknown_click_outcome_stops_without_replay(original, clock):

    def click(driver):
        raise original

    driver = Driver(click)
    with pytest.raises(OperationRetryError) as failure:
        click_with_retry(driver, ("id", "button"), is_complete=lambda d: False)
    assert failure.value.reason == "uncertain_outcome" and driver.clicks == 1
    assert failure.value.__cause__ is original


def test_failed_click_verification_does_not_replay(clock):
    original, verification_error = StaleElementReferenceException("replaced"), RuntimeError("cannot verify")

    def click(driver):
        raise original

    driver = Driver(click)

    def complete(current):
        if current.clicks:
            raise verification_error
        return False

    with pytest.raises(OperationRetryError) as failure:
        click_with_retry(driver, ("id", "button"), is_complete=complete)
    assert failure.value.reason == "verification_failed" and driver.clicks == 1
    assert failure.value.last_error is original and failure.value.__cause__ is verification_error


def test_successful_click_without_confirmed_completion_times_out_without_replay(clock):
    driver = Driver(lambda d: None)
    with pytest.raises(OperationRetryTimeoutError):
        click_with_retry(driver, ("id", "button"), is_complete=lambda d: False, timeout=0.2)
    assert driver.clicks == 1


def test_click_recovery_receives_driver_and_error(clock):
    recovered = []

    def click(driver):
        if not recovered:
            raise ElementClickInterceptedException("overlay")
        driver.complete = True

    driver = Driver(click)
    assert click_with_retry(driver, ("id", "button"), is_complete=lambda d: d.complete,
                            recover=lambda d, e, t: recovered.append((d, e, t)))
    assert recovered[0][0] is driver and isinstance(recovered[0][1], ElementClickInterceptedException)
    assert driver.clicks == 2


def test_failed_attempt_results_are_not_added_to_collection(clock):
    calls, records = [], {}

    def read(seconds):
        local_result = {"id": "one", "attempt": len(calls) + 1}
        calls.append(True)
        if len(calls) < 3:
            raise StaleElementReferenceException("discard local partial data")
        return local_result

    result = retry_operation(read)
    records.setdefault(result["id"], result)  # Caller owns collection and identity.
    assert records == {"one": {"id": "one", "attempt": 3}}


def test_nested_retry_is_rejected_before_inner_action(clock):
    inner = []
    with pytest.raises(InvalidInputError, match="Cannot nest"):
        retry_operation(lambda _: retry_operation(lambda _: inner.append(True)))
    assert inner == []
    assert retry_operation(lambda _: "scope reset") == "scope reset"


@pytest.mark.parametrize("inner", [
    lambda: retry_operation(lambda _: True),
    lambda: wait_until(Driver(lambda d: None), lambda _: True),
    lambda: expand_short_url("https://maps.app.goo.gl/example"),
])
def test_wait_predicate_cannot_start_another_controller(inner, clock):
    with pytest.raises(InvalidInputError, match="Cannot nest"):
        wait_until(Driver(lambda d: None), lambda _: inner())


def test_short_url_cannot_be_wrapped_with_another_retry(monkeypatch, clock):
    def forbidden():
        pytest.fail("Nested short URL must fail before network I/O")

    monkeypatch.setattr(urls, "_make_opener", forbidden)
    with pytest.raises(InvalidInputError, match="Cannot nest"):
        retry_operation(lambda _: expand_short_url("https://maps.app.goo.gl/example"))
    full = "https://www.google.com/maps/place/Example"
    assert retry_operation(lambda _: expand_short_url(full)) == full


def test_wait_is_allowed_inside_single_retry_controller(clock):
    driver = Driver(lambda d: None)
    assert retry_operation(lambda seconds: wait_until(driver, lambda _: True, timeout=seconds))


def test_click_helper_cannot_be_wrapped_with_a_second_retry(clock):
    driver = Driver(lambda d: None)
    with pytest.raises(InvalidInputError, match="Cannot nest"):
        retry_operation(lambda seconds: click_with_retry(driver, ("id", "button"), is_complete=lambda d: False))
    assert driver.finds == driver.clicks == 0


def test_url_strategy_cannot_start_another_retry(monkeypatch, clock):
    calls = []
    monkeypatch.setattr(urls, "_make_opener", lambda: object())
    monkeypatch.setattr(urls, "_http_expand", lambda *args: retry_operation(lambda _: calls.append(True)))
    with pytest.raises(InvalidInputError, match="Cannot nest"):
        expand_short_url("https://maps.app.goo.gl/example")
    assert calls == [] and retry_operation(lambda _: True)


def test_base_exception_restores_controller_scope(clock):
    def interrupted(seconds):
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        retry_operation(interrupted)
    assert retry_operation(lambda _: True)


@pytest.mark.parametrize("options", [
    {"max_retries": -1}, {"max_retries": 4}, {"max_retries": True}, {"max_retries": 1.5},
    {"timeout": 0}, {"timeout": float("inf")}, {"timeout": True},
    {"operation": ""}, {"locator": ("id", "")}, {"recover": False},
])
def test_invalid_parameters_fail_before_action(options):
    calls = []
    with pytest.raises(InvalidInputError):
        retry_operation(lambda _: calls.append(True), **options)
    assert calls == []


def test_invalid_callbacks_and_click_driver_are_rejected(clock):
    with pytest.raises(InvalidInputError):
        retry_operation(None)
    with pytest.raises(InvalidInputError):
        click_with_retry(None, ("id", "x"), is_complete=None)
    driver = Driver(lambda d: None)
    driver.timeouts.implicit_wait = 1
    with pytest.raises(InvalidInputError):
        click_with_retry(driver, ("id", "x"), is_complete=lambda d: False)
    assert driver.clicks == 0

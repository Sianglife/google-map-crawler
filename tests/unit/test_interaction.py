"""Required waits, fresh lookup and error context using a deterministic clock."""

from types import SimpleNamespace

import pytest
from selenium.common.exceptions import (
    InvalidSelectorException, InvalidSessionIdException, NoSuchElementException,
    StaleElementReferenceException, TimeoutException,
)
from selenium.webdriver.support import wait as selenium_wait

from google_map_crawler import CrawlerError, PageLoadTimeoutError, PageWaitError, ParseError
from google_map_crawler import interaction
from google_map_crawler.exceptions import InvalidInputError


LOCATOR = ("id", "target")


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


class Element:
    def __init__(self, *, visible=True, enabled=True, stale=False):
        self.visible = visible
        self.enabled = enabled
        self.stale = stale

    def is_displayed(self):
        if self.stale:
            raise StaleElementReferenceException("replaced node")
        return self.visible

    def is_enabled(self):
        return self.enabled


class Driver:
    def __init__(self, *outcomes, implicit=0):
        self.timeouts = SimpleNamespace(implicit_wait=implicit)
        self.outcomes = list(outcomes) or [NoSuchElementException("missing node")]
        self.calls = []

    def find_element(self, by, value):
        self.calls.append((by, value))
        result = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(result, BaseException):
            raise result
        return result


@pytest.mark.parametrize("state", ["present", "visible", "clickable"])
def test_ready_element_is_returned_without_polling_again(state, clock):
    element = Element()
    driver = Driver(element)
    assert interaction.wait_for_element(driver, LOCATOR, state=state) is element
    assert driver.calls == [LOCATOR] and clock.now == 0


def test_presence_accepts_hidden_disabled_element(clock):
    element = Element(visible=False, enabled=False)
    assert interaction.wait_for_element(Driver(element), LOCATOR, state="present") is element


def test_visibility_does_not_require_enabled(clock):
    element = Element(enabled=False)
    assert interaction.wait_for_element(Driver(element), LOCATOR) is element


@pytest.mark.parametrize("state,first", [
    ("present", NoSuchElementException("not inserted yet")),
    ("visible", Element(visible=False)),
    ("clickable", Element(enabled=False)),
    ("visible", Element(stale=True)),
    ("clickable", StaleElementReferenceException("replaced node")),
])
def test_pending_or_stale_state_reacquires_the_element(state, first, clock):
    final = Element()
    driver = Driver(first, final)
    assert interaction.wait_for_element(driver, LOCATOR, state=state) is final
    assert driver.calls == [LOCATOR, LOCATOR] and clock.now == pytest.approx(0.1)


@pytest.mark.parametrize("state,element", [
    ("visible", Element(visible=False)), ("clickable", Element(enabled=False)),
])
def test_unsatisfied_required_states_raise_timeout(state, element, clock):
    with pytest.raises(PageLoadTimeoutError):
        interaction.wait_for_element(Driver(element), LOCATOR, state=state, timeout=0.25)
    assert clock.now < 0.4


def test_timeout_preserves_context_selenium_cause_and_last_pending_error(clock):
    pending = NoSuchElementException("detail not ready")
    with pytest.raises(PageLoadTimeoutError) as failure:
        interaction.wait_for_element(Driver(pending), LOCATOR, timeout=0.25, operation="load_detail")
    error = failure.value
    assert isinstance(error, PageWaitError) and isinstance(error, CrawlerError)
    assert (error.operation, error.locator, error.state, error.timeout) == ("load_detail", LOCATOR, "visible", 0.25)
    assert isinstance(error.__cause__, TimeoutException) and error.last_error is pending
    assert "load_detail" in str(error) and "target" in str(error)


def test_custom_condition_returns_original_truthy_result(clock):
    expected = {"ready": True}
    outcomes = iter([False, None, [], expected])
    driver = Driver()
    received = []

    def predicate(current):
        received.append(current)
        return next(outcomes)

    assert interaction.wait_until(driver, predicate) is expected
    assert received == [driver] * 4 and clock.now == pytest.approx(0.3)


def test_custom_wait_timeout_is_an_error_not_an_empty_result(clock):
    with pytest.raises(PageLoadTimeoutError) as failure:
        interaction.wait_until(Driver(), lambda _: [], timeout=0.2, operation="ready", locator=LOCATOR)
    assert failure.value.state == "custom" and failure.value.last_error is None


@pytest.mark.parametrize("original", [InvalidSelectorException("bad CSS"), InvalidSessionIdException("closed")])
def test_terminal_selenium_errors_fail_immediately(original, clock):
    driver = Driver(original)
    with pytest.raises(PageWaitError) as failure:
        interaction.wait_for_element(driver, LOCATOR)
    assert not isinstance(failure.value, PageLoadTimeoutError)
    assert failure.value.__cause__ is original and driver.calls == [LOCATOR]
    assert failure.value.locator == LOCATOR and clock.now == 0


@pytest.mark.parametrize("original", [ParseError("invalid data"), RuntimeError("predicate bug"), KeyboardInterrupt()])
def test_callback_errors_are_not_suppressed_or_retried(original, clock):
    calls = []

    def predicate(_):
        calls.append(True)
        raise original

    with pytest.raises(type(original)) as failure:
        interaction.wait_until(Driver(), predicate)
    assert failure.value is original and calls == [True] and clock.now == 0


def test_a_late_success_cannot_exceed_the_same_wait_budget(clock):
    def predicate(_):
        clock.now += 1
        return True

    with pytest.raises(PageLoadTimeoutError):
        interaction.wait_until(Driver(), predicate, timeout=0.5)


@pytest.mark.parametrize("implicit", [0.1, 10])
def test_nonzero_implicit_wait_is_rejected_without_mutating_driver(implicit, clock):
    driver = Driver(Element(), implicit=implicit)
    with pytest.raises(InvalidInputError, match="implicit wait must be 0"):
        interaction.wait_for_element(driver, LOCATOR)
    assert driver.calls == [] and driver.timeouts.implicit_wait == implicit


@pytest.mark.parametrize("options", [
    {"timeout": 0}, {"timeout": -1}, {"timeout": True}, {"timeout": "1"},
    {"timeout": float("inf")}, {"timeout": float("nan")}, {"timeout": 10**1000},
    {"operation": ""}, {"operation": " "}, {"operation": None},
    {"state": "enabled"}, {"state": []},
])
def test_invalid_element_wait_arguments_fail_before_driver_io(options):
    class ForbiddenDriver:
        @property
        def timeouts(self):
            pytest.fail("Invalid arguments must not access driver timeouts")

    with pytest.raises(InvalidInputError):
        interaction.wait_for_element(ForbiddenDriver(), LOCATOR, **options)


@pytest.mark.parametrize("locator", [None, [], ["id", "a"], ("id",), ("id", "a", "b"), ([], "a"), ("id", ""), ("unknown", "a")])
def test_invalid_locator_fails_without_driver_access(locator):
    with pytest.raises(InvalidInputError):
        interaction.wait_for_element(None, locator)


@pytest.mark.parametrize("options", [{"condition": None}, {"timeout": False}, {"locator": ("id", "")}, {"operation": ""}])
def test_custom_wait_arguments_are_validated_before_driver_access(options):
    kwargs = {"condition": lambda _: True, **options}
    with pytest.raises(InvalidInputError):
        interaction.wait_until(None, **kwargs)


def test_missing_driver_contract_is_an_input_error(clock):
    with pytest.raises(InvalidInputError, match="timeouts"):
        interaction.wait_until(None, lambda _: True)
    with pytest.raises(InvalidInputError, match="find_element"):
        interaction.wait_for_element(SimpleNamespace(timeouts=SimpleNamespace(implicit_wait=0)), LOCATOR)

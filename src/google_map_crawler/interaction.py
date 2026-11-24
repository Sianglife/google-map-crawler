"""Explicit waits and bounded operations with guarded click recovery."""

from __future__ import annotations

import errno
import socket
from time import monotonic
from typing import TYPE_CHECKING, Callable, Literal, TypeVar
from urllib.error import URLError

from ._control import control_scope
from .exceptions import (
    CrawlerError, InvalidInputError, OperationRetryError, OperationRetryTimeoutError,
    PageLoadTimeoutError, PageWaitError,
)
from .validation import validate_count, validate_non_empty_string, validate_positive_timeout

if TYPE_CHECKING:
    from selenium.webdriver.remote.webdriver import WebDriver
    from selenium.webdriver.remote.webelement import WebElement


T = TypeVar("T")
Locator = tuple[str, str]
_LOCATORS = {
    "id", "xpath", "link text", "partial link text", "name",
    "tag name", "class name", "css selector",
}
_STATES = {"present", "visible", "clickable"}


def _check_implicit_wait(driver):
    timeouts = getattr(driver, "timeouts", None)
    if timeouts is None or getattr(timeouts, "implicit_wait", None) is None:
        raise InvalidInputError("driver must expose timeouts.implicit_wait")
    if timeouts.implicit_wait != 0:
        raise InvalidInputError("driver implicit wait must be 0 for explicit waits")


def _validate_locator(locator: Locator) -> None:
    if not isinstance(locator, tuple) or len(locator) != 2:
        raise InvalidInputError("locator must be a (by, value) tuple")
    by, value = locator
    validate_non_empty_string(by, name="locator.by")
    validate_non_empty_string(value, name="locator.value")
    if by not in _LOCATORS:
        raise InvalidInputError("locator.by must be a standard Selenium locator strategy")


def _wait(
    driver: WebDriver, condition: Callable[[WebDriver], T], *, timeout: float,
    operation: str, locator: Locator | None, state: str,
) -> T:
    timeout = validate_positive_timeout(timeout, name="timeout")
    validate_non_empty_string(operation, name="operation")
    if not callable(condition):
        raise InvalidInputError("condition must be callable")
    if locator is not None:
        _validate_locator(locator)

    # Importing this module alone never loads Selenium or starts a driver.
    from selenium.common.exceptions import (
        NoSuchElementException, StaleElementReferenceException,
        TimeoutException, WebDriverException,
    )
    from selenium.webdriver.support.ui import WebDriverWait

    deadline = monotonic() + timeout
    last_error = None
    context = dict(operation=operation, locator=locator, state=state, timeout=timeout)
    description = f"{operation}: state={state}, locator={locator!r}, timeout={timeout:g}s"

    def check_deadline():
        if monotonic() >= deadline:
            raise TimeoutException("Condition wait time budget expired")

    def probe(current_driver):
        nonlocal last_error
        check_deadline()
        try:
            result = condition(current_driver)
        except (NoSuchElementException, StaleElementReferenceException) as error:
            last_error = error
            return False
        check_deadline()
        return result

    try:
        _check_implicit_wait(driver)
        check_deadline()
        return WebDriverWait(driver, deadline - monotonic(), poll_frequency=0.1).until(probe)
    except TimeoutException as error:
        raise PageLoadTimeoutError(
            "Timed out waiting for " + description, last_error=last_error, **context,
        ) from error
    except WebDriverException as error:
        raise PageWaitError("Failed waiting for " + description, last_error=last_error, **context) from error


def wait_until(
    driver: WebDriver, condition: Callable[[WebDriver], T], *, timeout: float = 10,
    operation: str = "wait_until", locator: Locator | None = None,
) -> T:
    """Return the first truthy predicate result; predicates must be safe to poll.

    Missing/stale elements are polled within one deadline. Other exceptions are
    not suppressed. A supplied locator is diagnostic; the predicate must find
    fresh elements itself rather than capture a stale WebElement.
    """
    with control_scope("wait"):
        return _wait(driver, condition, timeout=timeout, operation=operation, locator=locator, state="custom")


def wait_for_element(
    driver: WebDriver, locator: Locator, *,
    state: Literal["present", "visible", "clickable"] = "visible",
    timeout: float = 10, operation: str = "wait_for_element",
) -> WebElement:
    """Find a fresh element on every poll; clickable means visible and enabled.

    This does not test overlays or perform clicks. All three states are required
    waits: timeout is an error, never evidence that an optional field is absent.
    """
    _validate_locator(locator)
    if not isinstance(state, str) or state not in _STATES:
        raise InvalidInputError("state must be present, visible or clickable")

    def condition(current_driver):
        if not callable(getattr(current_driver, "find_element", None)):
            raise InvalidInputError("driver must provide find_element")
        element = current_driver.find_element(*locator)
        if state == "present":
            return element
        if not element.is_displayed():
            return False
        if state == "clickable" and not element.is_enabled():
            return False
        return element

    with control_scope("wait"):
        return _wait(driver, condition, timeout=timeout, operation=operation, locator=locator, state=state)


def _rejected_click(error: BaseException) -> bool:
    from selenium.common.exceptions import (
        ElementClickInterceptedException, ElementNotInteractableException,
        StaleElementReferenceException,
    )
    return isinstance(error, (
        StaleElementReferenceException, ElementClickInterceptedException,
        ElementNotInteractableException,
    ))


def _retryable(error: Exception) -> bool:
    if isinstance(error, PageLoadTimeoutError):
        return False  # One completed wait must not silently acquire a new deadline.
    if isinstance(error, PageWaitError):
        return _rejected_click(error.__cause__)
    if isinstance(error, CrawlerError):
        return False
    if _rejected_click(error):
        return True
    reason = error.reason if isinstance(error, URLError) else error
    return isinstance(reason, TimeoutError) or (
        isinstance(reason, OSError) and reason.errno in {
            errno.ECONNRESET, errno.ECONNABORTED, errno.ECONNREFUSED,
            errno.ETIMEDOUT, socket.EAI_AGAIN,
        }
    )


def retry_operation(
    action: Callable[[float], T], *, max_retries: int = 3, timeout: float = 30,
    operation: str = "retry_operation", locator: Locator | None = None,
    recover: Callable[[Exception, float], None] | None = None,
) -> T:
    """Run a replay-safe action with a single attempt/time budget.

    action(remaining_seconds) must return data rather than append partial results
    externally. recover(error, remaining_seconds) may restore a known state before
    the next attempt. Falsy return values are valid successes. For page-changing
    clicks, use click_with_retry and an explicit completion check.
    """
    timeout = validate_positive_timeout(timeout, name="timeout")
    if validate_count(max_retries, name="max_retries") > 3:
        raise InvalidInputError("max_retries must be between 0 and 3")
    validate_non_empty_string(operation, name="operation")
    if not callable(action) or (recover is not None and not callable(recover)):
        raise InvalidInputError("action and optional recover must be callable")
    if locator is not None:
        _validate_locator(locator)

    with control_scope("retry"):
        deadline = monotonic() + timeout
        attempts = 0
        last_error = None

        def failure(reason, cause, error_type=OperationRetryError):
            return error_type(
                f"{operation}: {reason} after {attempts} attempt(s); locator={locator!r}",
                operation=operation, attempts=attempts, max_retries=max_retries,
                timeout=timeout, locator=locator, reason=reason, last_error=cause,
            )

        def remaining():
            seconds = deadline - monotonic()
            if seconds <= 0:
                raise failure("timeout", last_error, OperationRetryTimeoutError) from last_error
            return seconds

        for attempt in range(1, max_retries + 2):
            seconds = remaining()
            attempts = attempt
            try:
                result = action(seconds)
            except Exception as error:
                if isinstance(error, PageLoadTimeoutError) and monotonic() >= deadline:
                    last_error = error
                    remaining()
                if not _retryable(error):
                    raise
                last_error = error
                remaining()
                if attempt == max_retries + 1:
                    raise failure("attempts_exhausted", error) from error
                if recover is not None:
                    try:
                        recover(error, remaining())
                    except Exception as recovery_error:
                        if monotonic() >= deadline:
                            raise failure("timeout", error, OperationRetryTimeoutError) from recovery_error
                        raise failure("recovery_failed", error) from recovery_error
                    remaining()
            else:
                remaining()
                return result


def click_with_retry(
    driver: WebDriver, locator: Locator, *, is_complete: Callable[[WebDriver], T],
    max_retries: int = 3, timeout: float = 30, operation: str = "click",
    recover: Callable[[WebDriver, Exception, float], None] | None = None,
) -> T:
    """Click a fresh element only after confirming the desired state is absent.

    A lost click acknowledgement is checked against is_complete before replay.
    Only explicitly rejected clicks may be repeated. Uncertain outcomes and
    failed verification stop immediately. Completion predicates must be read-only.
    """
    _validate_locator(locator)
    if not callable(is_complete) or (recover is not None and not callable(recover)):
        raise InvalidInputError("is_complete and optional recover must be callable")
    attempts = 0

    def action(seconds):
        nonlocal attempts
        attempts += 1
        deadline = monotonic() + seconds
        _check_implicit_wait(driver)

        def remaining():
            left = deadline - monotonic()
            if left <= 0:
                raise OperationRetryTimeoutError(
                    f"{operation}: click time budget expired", operation=operation,
                    attempts=attempts, max_retries=max_retries, timeout=timeout,
                    locator=locator, reason="timeout",
                )
            return left

        complete = is_complete(driver)
        if complete:
            return complete
        element = wait_for_element(
            driver, locator, state="clickable", timeout=remaining(), operation=operation,
        )
        from selenium.common.exceptions import WebDriverException

        try:
            element.click()
        except (WebDriverException, OSError, URLError) as click_error:
            try:
                complete = is_complete(driver)
            except Exception as verification_error:
                raise OperationRetryError(
                    f"{operation}: could not verify the failed click", operation=operation,
                    attempts=attempts, max_retries=max_retries, timeout=timeout,
                    locator=locator, reason="verification_failed", last_error=click_error,
                ) from verification_error
            if complete:
                return complete
            if _rejected_click(click_error):
                raise
            raise OperationRetryError(
                f"{operation}: click outcome is uncertain; refusing to replay", operation=operation,
                attempts=attempts, max_retries=max_retries, timeout=timeout,
                locator=locator, reason="uncertain_outcome", last_error=click_error,
            ) from click_error
        return wait_until(
            driver, is_complete, timeout=remaining(), operation=f"{operation}.complete", locator=locator,
        )

    recovery = None if recover is None else lambda error, seconds: recover(driver, error, seconds)
    return retry_operation(
        action, timeout=timeout, max_retries=max_retries, operation=operation,
        locator=locator, recover=recovery,
    )

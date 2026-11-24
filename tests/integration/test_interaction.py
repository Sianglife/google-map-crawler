"""Opt-in Chrome checks against local dynamic HTML, including stale node races."""

import os
from pathlib import Path

import pytest
from selenium.common.exceptions import (
    ElementClickInterceptedException, InvalidSelectorException, NoSuchElementException,
    StaleElementReferenceException, TimeoutException,
)
from selenium.webdriver.remote.webelement import WebElement

from google_map_crawler import OperationRetryError, OperationRetryTimeoutError, PageLoadTimeoutError, PageWaitError
from google_map_crawler.browser import BrowserConfig, BrowserSession
from google_map_crawler.interaction import click_with_retry, wait_for_element, wait_until


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("GOOGLE_MAP_CRAWLER_RUN_BROWSER_TESTS") != "1",
        reason="Set GOOGLE_MAP_CRAWLER_RUN_BROWSER_TESTS=1 to start real Chrome",
    ),
]
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "wait_states.html"


@pytest.fixture
def chrome(assert_process_exited):
    session = BrowserSession(BrowserConfig(page_load_timeout=10))
    process = pid = None
    try:
        with session as driver:
            process = driver.service.process
            pid = driver.capabilities.get("goog:processID")
            assert isinstance(pid, int)
            driver.get(FIXTURE.as_uri())
            yield driver
    finally:
        assert session.cleanup_errors == ()
        if process is not None:
            assert process.poll() is not None, "Owned ChromeDriver is still running"
            assert_process_exited(pid)


def test_real_presence_visibility_enabled_and_overlay_states(chrome):
    hidden = wait_for_element(chrome, ("id", "hidden"), state="present")
    assert not hidden.is_displayed()
    with pytest.raises(PageLoadTimeoutError):
        wait_for_element(chrome, ("id", "hidden"), state="visible", timeout=0.2)
    chrome.execute_script("window.reveal()")
    assert wait_for_element(chrome, ("id", "hidden"), timeout=3).is_displayed()

    disabled = wait_for_element(chrome, ("id", "disabled"), state="visible")
    assert not disabled.is_enabled()
    with pytest.raises(PageLoadTimeoutError):
        wait_for_element(chrome, ("id", "disabled"), state="clickable", timeout=0.2)
    chrome.execute_script("window.enable()")
    assert wait_for_element(chrome, ("id", "disabled"), state="clickable", timeout=3).is_enabled()

    covered = wait_for_element(chrome, ("id", "covered"), state="clickable")
    assert chrome.find_element("id", "overlay").is_displayed()
    assert chrome.execute_script("return window.clicks") == 0  # Helpers never click.
    chrome.execute_script("window.uncover()")
    assert wait_until(chrome, lambda driver: not driver.find_elements("id", "overlay"), timeout=3)
    covered.click()
    assert chrome.execute_script("return window.clicks") == 1
    assert chrome.timeouts.implicit_wait == 0
    print(
        f"\nChrome {chrome.capabilities['browserVersion']}; "
        f"ChromeDriver {chrome.capabilities['chrome']['chromedriverVersion'].split()[0]}"
    )


@pytest.mark.parametrize("state", ["visible", "clickable"])
def test_real_stale_element_is_relocated(chrome, monkeypatch, state):
    original_find = chrome.find_element
    returned = []

    def find_then_replace(by, value):
        element = original_find(by, value)
        returned.append(element)
        if len(returned) == 1:
            # Change the actual DOM after locating but before the state check.
            chrome.execute_script("window.replaceNode(arguments[0])", element)
        return element

    monkeypatch.setattr(chrome, "find_element", find_then_replace)
    element = wait_for_element(chrome, ("id", "replace"), state=state, timeout=3)
    assert len(returned) == 2 and element.id != returned[0].id
    assert element.text == "Replace this node"


def test_real_required_ready_and_missing_optional_field(chrome):
    def detail_ready(driver):
        element = driver.find_element("id", "detail")
        return element if element.get_attribute("data-ready") == "true" else False

    with pytest.raises(PageLoadTimeoutError):
        wait_until(chrome, detail_ready, timeout=0.2, operation="detail_ready")
    chrome.execute_script("window.loadDetail()")
    panel = wait_until(chrome, detail_ready, timeout=3, operation="detail_ready")
    assert panel.is_displayed()
    phones = panel.find_elements("css selector", "[data-field='phone']")
    phone = phones[0].text if phones else None
    assert phone is None

    with pytest.raises(PageLoadTimeoutError) as failure:
        wait_for_element(chrome, ("id", "missing-required"), timeout=0.2, operation="required_field")
    assert isinstance(failure.value.last_error, NoSuchElementException)
    assert failure.value.operation == "required_field"


def test_real_invalid_selector_is_not_polled_until_timeout(chrome):
    with pytest.raises(PageWaitError) as failure:
        wait_for_element(chrome, ("css selector", "["), timeout=3, operation="bad_selector")
    assert not isinstance(failure.value, PageLoadTimeoutError)
    assert isinstance(failure.value.__cause__, InvalidSelectorException)


def test_real_persistent_stale_uses_one_deadline(chrome):
    def always_replaced(driver):
        element = driver.find_element("id", "replace")
        driver.execute_script("window.replaceNode(arguments[0])", element)
        return element.is_displayed()

    with pytest.raises(PageLoadTimeoutError) as failure:
        wait_until(chrome, always_replaced, timeout=0.4, operation="unstable_detail", locator=("id", "replace"))
    assert isinstance(failure.value.last_error, StaleElementReferenceException)


def clicked(driver):
    return driver.execute_script("return window.clicks === 1")


def test_real_click_recovers_from_overlay_without_duplicate_event(chrome):
    recoveries = []

    def recover(driver, error, seconds):
        assert isinstance(error, ElementClickInterceptedException)
        recoveries.append(error)
        driver.execute_script("window.uncover()")
        wait_until(driver, lambda d: not d.find_elements("id", "overlay"), timeout=seconds)

    assert click_with_retry(chrome, ("id", "covered"), is_complete=clicked, recover=recover, timeout=10)
    assert len(recoveries) == 1 and chrome.execute_script("return window.clicks") == 1


def test_real_stale_click_relocates_before_retry(chrome, monkeypatch):
    chrome.execute_script("document.getElementById('overlay').remove()")
    original_click = WebElement.click
    calls = []

    def replaced_click(element):
        calls.append(element.id)
        if len(calls) == 1:
            chrome.execute_script("window.replaceNode(arguments[0])", element)
        return original_click(element)  # Chrome raises actual stale on the first call.

    monkeypatch.setattr(WebElement, "click", replaced_click)
    assert click_with_retry(chrome, ("id", "covered"), is_complete=clicked, timeout=10)
    assert len(calls) == 2 and calls[0] != calls[1]
    assert chrome.execute_script("return window.clicks") == 1


def test_real_applied_click_with_lost_acknowledgement_is_not_repeated(chrome, monkeypatch):
    chrome.execute_script("document.getElementById('overlay').remove()")
    original_click = WebElement.click
    calls = []

    def lost_acknowledgement(element):
        calls.append(element.id)
        original_click(element)
        raise TimeoutException("injected lost acknowledgement after an actual Chrome click")

    monkeypatch.setattr(WebElement, "click", lost_acknowledgement)
    assert click_with_retry(chrome, ("id", "covered"), is_complete=clicked, timeout=10)
    assert click_with_retry(chrome, ("id", "covered"), is_complete=clicked, timeout=10)
    assert len(calls) == 1 and chrome.execute_script("return window.clicks") == 1


def test_real_failed_verification_stops_after_applied_click(chrome, monkeypatch):
    chrome.execute_script("document.getElementById('overlay').remove()")
    original_click = WebElement.click
    calls = []

    def lost_acknowledgement(element):
        calls.append(element.id)
        original_click(element)
        raise TimeoutException("injected lost acknowledgement")

    def cannot_verify(driver):
        if driver.execute_script("return window.clicks"):
            raise RuntimeError("injected completion-check failure")
        return False

    monkeypatch.setattr(WebElement, "click", lost_acknowledgement)
    with pytest.raises(OperationRetryError) as failure:
        click_with_retry(chrome, ("id", "covered"), is_complete=cannot_verify, timeout=10)
    assert failure.value.reason == "verification_failed" and len(calls) == 1
    assert chrome.execute_script("return window.clicks") == 1


def test_real_blocked_click_exhausts_its_attempt_budget(chrome):
    with pytest.raises(OperationRetryError) as failure:
        click_with_retry(chrome, ("id", "covered"), is_complete=clicked, max_retries=1, timeout=10)
    assert failure.value.reason == "attempts_exhausted" and failure.value.attempts == 2
    assert isinstance(failure.value.__cause__, ElementClickInterceptedException)
    assert chrome.execute_script("return window.clicks") == 0


def test_real_completion_timeout_does_not_repeat_a_successful_click(chrome):
    chrome.execute_script("document.getElementById('overlay').remove()")
    with pytest.raises(OperationRetryTimeoutError):
        click_with_retry(chrome, ("id", "covered"), is_complete=lambda d: False, timeout=0.5)
    assert chrome.execute_script("return window.clicks") == 1

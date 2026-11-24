"""Opt-in real Chrome checks for owned resources, including failure cleanup."""

import os
from urllib.parse import quote

import pytest

from google_map_crawler.browser import BrowserConfig, BrowserSession


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("GOOGLE_MAP_CRAWLER_RUN_BROWSER_TESTS") != "1",
        reason="Set GOOGLE_MAP_CRAWLER_RUN_BROWSER_TESTS=1 to start real Chrome",
    ),
]


@pytest.mark.parametrize("fail_in_body", [False, True], ids=["normal", "body-error"])
def test_real_chrome_configuration_and_cleanup(fail_in_body, assert_process_exited):
    session = BrowserSession(BrowserConfig(language="en-US", page_load_timeout=10))
    original = RuntimeError("intentional smoke-test failure")
    chrome_pid = None
    service_process = None
    try:
        with session as driver:
            service_process = driver.service.process
            chrome_pid = driver.capabilities.get("goog:processID")
            assert isinstance(chrome_pid, int), "Chrome did not expose its owned process ID"
            driver.get("data:text/html;charset=utf-8," + quote(
                "<title>BrowserSession smoke</title><p id='smoke'>local page ready</p>"
            ))
            assert driver.title == "BrowserSession smoke"
            assert driver.find_element("id", "smoke").text == "local page ready"
            assert driver.execute_script("return navigator.language") == "en-US"
            assert driver.timeouts.page_load == 10
            assert driver.timeouts.implicit_wait == 0
            if fail_in_body:
                raise original
    except RuntimeError as error:
        assert fail_in_body and error is original
    else:
        assert not fail_in_body

    assert session.cleanup_errors == ()
    assert service_process.poll() is not None, "Owned ChromeDriver is still running"
    assert_process_exited(chrome_pid)

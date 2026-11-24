"""Opt-in real Chrome checks for owned resources, including failure cleanup."""

import os
import time
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


def assert_process_exited(pid):
    """Check only the process created by this test, without terminating anything."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle:
            assert ctypes.get_last_error() == 87, "Cannot inspect owned Chrome process"
            return
        try:
            assert kernel.WaitForSingleObject(handle, 5000) == 0, "Owned Chrome is still running"
        finally:
            kernel.CloseHandle(handle)
        return
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    pytest.fail("Owned Chrome is still running")


@pytest.mark.parametrize("fail_in_body", [False, True], ids=["normal", "body-error"])
def test_real_chrome_configuration_and_cleanup(fail_in_body):
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

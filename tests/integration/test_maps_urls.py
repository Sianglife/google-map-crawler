"""Opt-in public-link verification; public Maps access can change over time."""

import os

import pytest

from google_map_crawler import expand_short_url
from google_map_crawler.browser import BrowserConfig, BrowserSession


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("GOOGLE_MAP_CRAWLER_RUN_MAPS_TESTS") != "1",
        reason="Set GOOGLE_MAP_CRAWLER_RUN_MAPS_TESTS=1 to access public Google Maps links",
    ),
]

# Taiwan government-provided ESC29 administrative circular, pages 6-7:
# https://www.ccsbt.org/system/files/2024-06/AdministrativeCircular_ESC29_provided_by_TW_government.pdf
SAMPLES = [
    pytest.param("https://maps.app.goo.gl/EGSCc4KavHEFuwVZ7", ("國立故宮博物院", "nationalpalacemuseum"), id="national-palace-museum"),
    pytest.param("https://maps.app.goo.gl/PrYs3qc14ipRMSHu7", ("台北101", "臺北101", "taipei101"), id="taipei-101"),
]


@pytest.mark.parametrize("short_url,expected_names", SAMPLES)
def test_public_short_link_reaches_expected_place(short_url, expected_names, assert_process_exited):
    from selenium.webdriver.support.ui import WebDriverWait

    expanded = expand_short_url(short_url, timeout=30)
    assert expanded != short_url
    session = BrowserSession(BrowserConfig(page_load_timeout=30))
    process = pid = None
    try:
        with session as driver:
            process = driver.service.process
            pid = driver.capabilities.get("goog:processID")
            assert isinstance(pid, int)
            driver.get(expanded)

            def expected_place_visible(driver):
                headings = ["".join(element.text.split()).casefold() for element in driver.find_elements("css selector", "h1")]
                return any(expected.casefold() in heading for heading in headings for expected in expected_names)

            WebDriverWait(driver, 15).until(expected_place_visible)
            print(
                f"\n{short_url} -> {expanded}"
                f"\nheading: {driver.find_element('css selector', 'h1').text}"
                f"\nChrome: {driver.capabilities['browserVersion']}; "
                f"ChromeDriver: {driver.capabilities['chrome']['chromedriverVersion'].split()[0]}"
            )
    finally:
        assert session.cleanup_errors == ()
        if process is not None:
            assert process.poll() is not None
            assert_process_exited(pid)

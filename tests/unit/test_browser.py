"""Configuration boundaries and ownership of successful/failed sessions."""

from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from google_map_crawler.browser import BrowserConfig, BrowserSession
from google_map_crawler.exceptions import BrowserCleanupError, BrowserStartError, InvalidInputError


class FakeService:
    def __init__(self, events, error=None):
        self.events = events
        self.error = error

    def stop(self):
        self.events.append("stop")
        if self.error:
            raise self.error


class FakeDriver:
    def __init__(self, events, *, setup_error=None, quit_error=None, stop_error=None):
        self.events = events
        self.service = FakeService(events, stop_error)
        self.setup_error = setup_error
        self.quit_error = quit_error

    def set_page_load_timeout(self, timeout):
        self.events.append(("timeout", timeout))
        if self.setup_error:
            raise self.setup_error

    def implicitly_wait(self, timeout):
        self.events.append(("implicit", timeout))

    def quit(self):
        self.events.append("quit")
        if self.quit_error:
            raise self.quit_error


def test_default_configuration_and_immutability():
    config = BrowserConfig()
    assert (config.headless, config.language) == (True, "zh-TW")
    assert (config.page_load_timeout, config.wait_timeout) == (30, 10)
    assert (config.max_retries, config.no_progress_limit, config.max_scroll_rounds) == (3, 3, 100)
    with pytest.raises(FrozenInstanceError):
        config.headless = False


@pytest.mark.parametrize("name", ["page_load_timeout", "wait_timeout"])
@pytest.mark.parametrize("value", [0, -1, True, "10", None, float("nan"), float("inf"), 10**1000])
def test_invalid_timeouts_are_rejected_before_browser_work(name, value):
    with pytest.raises(InvalidInputError, match=name):
        BrowserConfig(**{name: value})


@pytest.mark.parametrize(
    "name,value",
    [("headless", 0), ("headless", "true"), ("language", ""), ("language", "  "),
     ("language", None), ("max_retries", -1), ("max_retries", 4), ("max_retries", True),
     ("max_retries", 1.5), ("no_progress_limit", 0), ("no_progress_limit", False),
     ("max_scroll_rounds", -1), ("max_scroll_rounds", 0), ("max_scroll_rounds", "100")],
)
def test_other_invalid_settings_report_the_field(name, value):
    with pytest.raises(InvalidInputError, match=name):
        BrowserConfig(**{name: value})


def test_custom_valid_configuration_accepts_zero_retries():
    config = BrowserConfig(headless=False, language="en-US", page_load_timeout=2.5,
                           wait_timeout=1, max_retries=0, no_progress_limit=1, max_scroll_rounds=5)
    assert config.headless is False
    assert config.page_load_timeout == 2.5
    assert config.wait_timeout == 1.0
    assert config.max_retries == 0


@pytest.mark.parametrize("kwargs", [{"config": {}}, {"driver_factory": 42}])
def test_session_rejects_invalid_arguments_on_construction(kwargs):
    with pytest.raises(InvalidInputError):
        BrowserSession(**kwargs)


def test_factory_runs_only_on_entry_and_resources_close_once_in_order():
    events = []
    driver = FakeDriver(events)
    config = BrowserConfig(page_load_timeout=7)

    def factory(received):
        assert received is config
        events.append("create")
        return driver

    session = BrowserSession(config, factory)
    assert events == []
    with pytest.raises(InvalidInputError, match="not active"):
        _ = session.driver
    with session as actual:
        assert actual is session.driver is driver
        assert events == ["create", ("timeout", 7), ("implicit", 0)]
    session.close()
    assert events == ["create", ("timeout", 7), ("implicit", 0), "quit", "stop"]
    assert session.cleanup_errors == ()
    with pytest.raises(InvalidInputError, match="not active"):
        _ = session.driver


def test_user_error_is_preserved_while_both_cleanup_failures_remain_inspectable():
    events = []
    quit_error, stop_error = RuntimeError("quit failed"), RuntimeError("stop failed")
    driver = FakeDriver(events, quit_error=quit_error, stop_error=stop_error)
    original = ValueError("scraping failed")
    session = BrowserSession(driver_factory=lambda _: driver)

    with pytest.raises(ValueError) as caught:
        with session:
            raise original

    assert caught.value is original
    assert session.cleanup_errors == (quit_error, stop_error)
    assert len(original.__notes__) == 2
    assert events[-2:] == ["quit", "stop"]
    session.close()
    assert events.count("quit") == events.count("stop") == 1


@pytest.mark.parametrize("failed_resource", ["quit", "stop", "both"])
def test_cleanup_only_failure_raises_with_all_causes(failed_resource):
    events = []
    quit_error = RuntimeError("quit failed") if failed_resource in ("quit", "both") else None
    stop_error = RuntimeError("stop failed") if failed_resource in ("stop", "both") else None
    session = BrowserSession(driver_factory=lambda _: FakeDriver(
        events, quit_error=quit_error, stop_error=stop_error
    ))

    with pytest.raises(BrowserCleanupError) as caught:
        with session:
            pass

    expected = tuple(item for item in (quit_error, stop_error) if item is not None)
    assert caught.value.errors == session.cleanup_errors == expected
    assert caught.value.__cause__ is expected[0]
    assert events[-2:] == ["quit", "stop"]


def test_configuration_failure_cleans_the_returned_driver_and_service():
    events = []
    original = RuntimeError("set timeout failed")
    driver = FakeDriver(events, setup_error=original, quit_error=RuntimeError("quit failed"))
    session = BrowserSession(driver_factory=lambda _: driver)

    with pytest.raises(BrowserStartError) as caught:
        with session:
            pytest.fail("Must not enter the body after setup failure")

    assert caught.value.__cause__ is original
    assert "quit failed" in caught.value.__notes__[0]
    assert events[-2:] == ["quit", "stop"]


def test_default_initialization_failure_stops_the_already_created_service(monkeypatch):
    import selenium.webdriver
    import selenium.webdriver.chrome.service

    events = []
    service = FakeService(events)
    original = RuntimeError("driver constructor failed after starting service")
    monkeypatch.setattr(selenium.webdriver.chrome.service, "Service", lambda **_: service)

    def failing_chrome(**kwargs):
        assert kwargs["service"] is service
        events.append("create")
        raise original

    monkeypatch.setattr(selenium.webdriver, "Chrome", failing_chrome)
    with pytest.raises(BrowserStartError) as caught:
        with BrowserSession():
            pytest.fail("Unreachable")

    assert caught.value.__cause__ is original
    assert events == ["create", "stop"]


@pytest.mark.parametrize("headless", [True, False])
def test_default_launch_applies_chrome_options_without_launching_a_real_browser(monkeypatch, headless):
    import os
    import subprocess
    import selenium.webdriver
    import selenium.webdriver.chrome.service

    events, service_options = [], {}
    service = FakeService(events)
    driver = FakeDriver(events)
    driver.service = service

    def make_service(**kwargs):
        service_options.update(kwargs)
        return service

    def chrome(**kwargs):
        assert kwargs["service"] is service
        options = kwargs["options"]
        assert ("--headless=new" in options.arguments) is headless
        assert "--lang=en-US" in options.arguments
        assert options.experimental_options["prefs"]["intl.accept_languages"] == "en-US"
        return driver

    monkeypatch.setattr(selenium.webdriver.chrome.service, "Service", make_service)
    monkeypatch.setattr(selenium.webdriver, "Chrome", chrome)
    with BrowserSession(BrowserConfig(headless=headless, language="en-US")):
        pass
    if os.name == "nt":
        assert service_options["popen_kw"]["creation_flags"] == subprocess.CREATE_NO_WINDOW
    assert events[-2:] == ["quit", "stop"]


def test_factory_failure_is_wrapped_without_starting_default_resources():
    original = RuntimeError("factory failed before handing anything over")

    def factory(config):
        raise original

    session = BrowserSession(driver_factory=factory)
    with pytest.raises(BrowserStartError) as caught:
        session.__enter__()
    assert caught.value.__cause__ is original
    assert session.cleanup_errors == ()
    session.close()


def test_single_use_session_rejects_nested_entry_and_reopening():
    events = []
    session = BrowserSession(driver_factory=lambda _: FakeDriver(events))
    with session:
        with pytest.raises(InvalidInputError, match="single-use"):
            session.__enter__()
        assert events[-1] == ("implicit", 0)
    with pytest.raises(InvalidInputError, match="single-use"):
        session.__enter__()
    assert events[-2:] == ["quit", "stop"]


def test_closing_before_entry_does_not_create_any_resources():
    session = BrowserSession(driver_factory=lambda _: pytest.fail("Must not start"))
    session.close()
    session.close()
    with pytest.raises(InvalidInputError, match="single-use"):
        session.__enter__()


@pytest.mark.parametrize("original", [KeyboardInterrupt(), SystemExit(2)])
def test_interrupt_during_initialization_cleans_owned_resources_and_is_preserved(original):
    events = []
    driver = FakeDriver(events, setup_error=original)
    session = BrowserSession(driver_factory=lambda _: driver)
    with pytest.raises(type(original)) as caught:
        session.__enter__()
    assert caught.value is original
    assert events[-2:] == ["quit", "stop"]


def test_interrupt_in_body_is_not_masked_by_cleanup():
    events = []
    original = KeyboardInterrupt()
    session = BrowserSession(driver_factory=lambda _: FakeDriver(events, quit_error=RuntimeError("quit")))
    with pytest.raises(KeyboardInterrupt) as caught:
        with session:
            raise original
    assert caught.value is original
    assert events[-2:] == ["quit", "stop"]


def test_driver_without_a_service_can_be_used_for_testing():
    events = []
    driver = SimpleNamespace(
        set_page_load_timeout=lambda _: None,
        implicitly_wait=lambda _: None,
        quit=lambda: events.append("quit"),
    )
    with BrowserSession(driver_factory=lambda _: driver):
        pass
    assert events == ["quit"]

"""Validated configuration and explicitly owned, single-use browser sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from .exceptions import BrowserCleanupError, BrowserStartError, InvalidInputError
from .validation import validate_count, validate_non_empty_string, validate_positive_timeout

if TYPE_CHECKING:
    from selenium.webdriver.chrome.webdriver import WebDriver


@dataclass(frozen=True, kw_only=True)
class BrowserConfig:
    """Settings only; constructing this object performs no browser work."""

    headless: bool = True
    language: str = "zh-TW"
    page_load_timeout: float = 30.0
    wait_timeout: float = 10.0
    max_retries: int = 3
    no_progress_limit: int = 3
    max_scroll_rounds: int = 100

    def __post_init__(self) -> None:
        if not isinstance(self.headless, bool):
            raise InvalidInputError("headless must be a boolean")
        validate_non_empty_string(self.language, name="language")
        for name in ("page_load_timeout", "wait_timeout"):
            object.__setattr__(self, name, validate_positive_timeout(getattr(self, name), name=name))
        if validate_count(self.max_retries, name="max_retries") > 3:
            raise InvalidInputError("max_retries must be between 0 and 3")
        for name in ("no_progress_limit", "max_scroll_rounds"):
            if validate_count(getattr(self, name), name=name) == 0:
                raise InvalidInputError(f"{name} must be a positive integer")


class BrowserSession:
    """Start on entry and release only resources handed to this session."""

    def __init__(
        self,
        config: BrowserConfig | None = None,
        driver_factory: Callable[[BrowserConfig], WebDriver] | None = None,
    ) -> None:
        if config is not None and not isinstance(config, BrowserConfig):
            raise InvalidInputError("config must be a BrowserConfig")
        if driver_factory is not None and not callable(driver_factory):
            raise InvalidInputError("driver_factory must be callable")
        self._config = config if config is not None else BrowserConfig()
        self._factory = driver_factory
        self._driver: WebDriver | None = None
        self._service: Any = None
        self._entered = False
        self._closed = False
        self._cleanup_errors: tuple[BaseException, ...] = ()

    @property
    def config(self) -> BrowserConfig:
        return self._config

    @property
    def driver(self) -> WebDriver:
        if self._driver is None or self._closed:
            raise InvalidInputError("BrowserSession is not active")
        return self._driver

    @property
    def cleanup_errors(self) -> tuple[BaseException, ...]:
        return self._cleanup_errors

    def _create_chrome_driver(self) -> WebDriver:
        # Even Selenium imports and Service construction are deferred until entry.
        import os
        import subprocess

        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service

        options = Options()
        options.add_argument(f"--lang={self.config.language}")
        options.add_experimental_option("prefs", {"intl.accept_languages": self.config.language})
        if self.config.headless:
            options.add_argument("--headless=new")
        popen_kw = {"creation_flags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        self._service = Service(popen_kw=popen_kw)
        return webdriver.Chrome(options=options, service=self._service)

    def __enter__(self) -> WebDriver:
        if self._entered or self._closed:
            raise InvalidInputError("BrowserSession is single-use and cannot be re-entered")
        self._entered = True
        try:
            if self._factory is None:
                self._driver = self._create_chrome_driver()
            else:
                self._driver = self._factory(self.config)
                self._service = getattr(self._driver, "service", None)
            if self._driver is None:
                raise InvalidInputError("driver_factory must return a new driver")
            self._driver.set_page_load_timeout(self.config.page_load_timeout)
            self._driver.implicitly_wait(0)
            return self._driver
        except BaseException as error:
            self._release()
            if not isinstance(error, Exception):
                self._annotate(error)
                raise
            failure = BrowserStartError("Failed to start or configure the browser")
            self._annotate(failure)
            raise failure from error

    def _release(self) -> None:
        if self._closed:
            return
        self._closed = True
        driver, self._driver = self._driver, None
        service, self._service = self._service, None
        errors: list[BaseException] = []
        if driver is not None:
            try:
                driver.quit()
            except BaseException as error:
                errors.append(error)
        if service is not None:
            try:
                service.stop()
            except BaseException as error:
                errors.append(error)
        self._cleanup_errors = tuple(errors)

    def _annotate(self, error: BaseException) -> None:
        for cleanup_error in self.cleanup_errors:
            error.add_note(
                f"Browser cleanup failed: {type(cleanup_error).__name__}: {cleanup_error}"
            )

    def _raise_cleanup_errors(self) -> None:
        if not self.cleanup_errors:
            return
        for error in self.cleanup_errors:
            if not isinstance(error, Exception):
                self._annotate(error)
                raise error
        raise BrowserCleanupError(errors=self.cleanup_errors) from self.cleanup_errors[0]

    def close(self) -> None:
        """Release resources once; retain failures for inspection after closing."""
        if self._closed:
            return
        self._release()
        self._raise_cleanup_errors()

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if self._closed:
            return False
        self._release()
        if exc is not None:
            self._annotate(exc)
        else:
            self._raise_cleanup_errors()
        return False

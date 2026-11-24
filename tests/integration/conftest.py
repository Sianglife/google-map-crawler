"""Process checks shared by opt-in tests of real, owned Chrome sessions."""

import os
import time

import pytest


@pytest.fixture
def assert_process_exited():
    def check(pid):
        """Inspect only a process created by the test; never terminate it."""
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

    return check

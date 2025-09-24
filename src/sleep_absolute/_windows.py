"""Windows implementation based on waitable timers."""
from __future__ import annotations

from typing import Optional
import asyncio as _asyncio
import datetime as _datetime
import math as _math
import ctypes as _ctypes
from ctypes import wintypes as _wintypes

__all__ = ["wait_until"]

_kernel32 = _ctypes.WinDLL("kernel32", use_last_error=True)  # pragma: no cover - windows only

_CreateWaitableTimerW = _kernel32.CreateWaitableTimerW  # pragma: no cover - windows only
_CreateWaitableTimerW.argtypes = (_ctypes.c_void_p, _wintypes.BOOL, _wintypes.LPCWSTR)
_CreateWaitableTimerW.restype = _wintypes.HANDLE

_SetWaitableTimer = _kernel32.SetWaitableTimer  # pragma: no cover - windows only
_SetWaitableTimer.argtypes = (
    _wintypes.HANDLE,
    _ctypes.POINTER(_ctypes.c_longlong),
    _wintypes.LONG,
    _ctypes.c_void_p,
    _ctypes.c_void_p,
    _wintypes.BOOL,
)
_SetWaitableTimer.restype = _wintypes.BOOL

_CloseHandle = _kernel32.CloseHandle  # pragma: no cover - windows only
_CloseHandle.argtypes = (_wintypes.HANDLE,)
_CloseHandle.restype = _wintypes.BOOL

_WINDOWS_TICK = 10_000_000
_EPOCH_DIFFERENCE_SECONDS = 11644473600


def _ensure_loop(loop: Optional[_asyncio.AbstractEventLoop]) -> _asyncio.AbstractEventLoop:
    if loop is not None:
        return loop
    try:
        return _asyncio.get_running_loop()
    except RuntimeError:
        return _asyncio.get_event_loop()


def _unix_to_windows_ticks(timestamp: float) -> int:
    whole, frac = _math.modf(timestamp)
    fractional_ticks = int(round(frac * _WINDOWS_TICK))
    whole_ticks = int(whole) * _WINDOWS_TICK
    if fractional_ticks >= _WINDOWS_TICK:
        whole_ticks += _WINDOWS_TICK
        fractional_ticks -= _WINDOWS_TICK
    return whole_ticks + fractional_ticks + _EPOCH_DIFFERENCE_SECONDS * _WINDOWS_TICK


def wait_until(
    target_time: _datetime.datetime,
    loop: Optional[_asyncio.AbstractEventLoop] = None,
) -> _asyncio.Future:
    """Return a future that resolves when ``target_time`` is reached."""
    loop = _ensure_loop(loop)
    proactor = getattr(loop, "_proactor", None)
    if proactor is None:
        raise RuntimeError("Event loop does not expose a Windows proactor")

    due_time_value = _ctypes.c_longlong(_unix_to_windows_ticks(target_time.timestamp()))

    handle = _CreateWaitableTimerW(None, True, None)
    if not handle:
        err = _ctypes.get_last_error()
        raise OSError(err, "Failed to create waitable timer")

    if not _SetWaitableTimer(handle, _ctypes.byref(due_time_value), 0, None, None, False):
        err = _ctypes.get_last_error()
        _CloseHandle(handle)
        raise OSError(err, "Failed to set waitable timer")

    future = proactor.wait_for_handle(handle, None)

    def _cleanup_callback(_fut: _asyncio.Future) -> None:
        _CloseHandle(handle)

    future.add_done_callback(_cleanup_callback)
    return future


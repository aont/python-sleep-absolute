"""Linux implementation backed by ``timerfd``."""
from __future__ import annotations

from typing import Optional
import asyncio as _asyncio
import datetime as _datetime
import math as _math
import os as _os
import ctypes as _ctypes

__all__ = ["wait_until"]

_libc = _ctypes.CDLL("libc.so.6", use_errno=True)

_CLOCK_REALTIME = 0
_TFD_NONBLOCK = 0o4000
_TFD_CLOEXEC = 0o2000000


class _Timespec(_ctypes.Structure):
    _fields_ = [("tv_sec", _ctypes.c_long), ("tv_nsec", _ctypes.c_long)]


class _Itimerspec(_ctypes.Structure):
    _fields_ = [("it_interval", _Timespec), ("it_value", _Timespec)]


_timerfd_create = _libc.timerfd_create
_timerfd_create.argtypes = (_ctypes.c_int, _ctypes.c_int)
_timerfd_create.restype = _ctypes.c_int

_timerfd_settime = _libc.timerfd_settime
_timerfd_settime.argtypes = (
    _ctypes.c_int,
    _ctypes.c_int,
    _ctypes.POINTER(_Itimerspec),
    _ctypes.POINTER(_Itimerspec),
)
_timerfd_settime.restype = _ctypes.c_int


def _ensure_loop(loop: Optional[_asyncio.AbstractEventLoop]) -> _asyncio.AbstractEventLoop:
    if loop is not None:
        return loop
    try:
        return _asyncio.get_running_loop()
    except RuntimeError:
        return _asyncio.get_event_loop()


def _create_timerfd() -> int:
    fd = _timerfd_create(_CLOCK_REALTIME, _TFD_NONBLOCK | _TFD_CLOEXEC)
    if fd == -1:
        err = _ctypes.get_errno()
        raise OSError(err, "Failed to create timerfd")
    return fd


def _program_timerfd(fd: int, target_time: _datetime.datetime) -> None:
    timestamp = target_time.timestamp()
    fractional, integral = _math.modf(timestamp)
    nanoseconds = int(round(fractional * 1_000_000_000))
    seconds = int(integral)
    if nanoseconds >= 1_000_000_000:
        seconds += 1
        nanoseconds -= 1_000_000_000

    new_value = _Itimerspec(
        it_interval=_Timespec(0, 0),
        it_value=_Timespec(seconds, nanoseconds),
    )
    if _timerfd_settime(fd, 1, _ctypes.byref(new_value), None) != 0:
        err = _ctypes.get_errno()
        raise OSError(err, "Failed to set timerfd")


def wait_until(
    target_time: _datetime.datetime,
    loop: Optional[_asyncio.AbstractEventLoop] = None,
) -> _asyncio.Future:
    """Return a future that resolves when ``target_time`` is reached."""
    loop = _ensure_loop(loop)
    add_reader = getattr(loop, "add_reader", None)
    remove_reader = getattr(loop, "remove_reader", None)
    if add_reader is None or remove_reader is None:
        raise RuntimeError("Event loop does not support file descriptor callbacks")

    fd = _create_timerfd()
    try:
        _program_timerfd(fd, target_time)
    except Exception:
        _os.close(fd)
        raise

    future = loop.create_future()
    closed = False

    def _close_fd() -> None:
        nonlocal closed
        if closed:
            return
        closed = True
        try:
            remove_reader(fd)
        finally:
            _os.close(fd)

    def _on_ready() -> None:
        if not future.done():
            future.set_result(None)
        _close_fd()

    try:
        add_reader(fd, _on_ready)
    except Exception:
        _close_fd()
        raise

    def _cleanup_callback(_fut: _asyncio.Future) -> None:
        _close_fd()

    future.add_done_callback(_cleanup_callback)
    return future


"""POSIX timer implementation based on ``timer_create``/``timer_settime``."""
from __future__ import annotations

from typing import Optional, Dict
import asyncio as _asyncio
import datetime as _datetime
import math as _math
import ctypes as _ctypes
import ctypes.util as _ctypes_util

__all__ = ["wait_until"]


def _load_timer_library() -> _ctypes.CDLL:
    candidates = []
    for library in ("rt", "c"):
        name = _ctypes_util.find_library(library)
        if name:
            candidates.append(name)
    candidates.extend(["librt.so.1", "librt.so", "libc.so.6"])
    last_error: Optional[OSError] = None
    for candidate in candidates:
        try:
            return _ctypes.CDLL(candidate, use_errno=True)
        except OSError as exc:  # pragma: no cover - depends on platform availability
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    raise OSError("Failed to locate librt/libc with timer functions")


_libc = _load_timer_library()

_CLOCK_REALTIME = 0
_TIMER_ABSTIME = 1
_SIGEV_THREAD = 2


class _Sigval(_ctypes.Union):
    _fields_ = [("sival_int", _ctypes.c_int), ("sival_ptr", _ctypes.c_void_p)]


_TimerCallback = _ctypes.CFUNCTYPE(None, _Sigval)


class _SigeventThread(_ctypes.Structure):
    _fields_ = [
        ("sigev_notify_function", _TimerCallback),
        ("sigev_notify_attributes", _ctypes.c_void_p),
    ]


class _SigeventUnion(_ctypes.Union):
    _fields_ = [
        ("_sigev_thread", _SigeventThread),
        ("_pad", _ctypes.c_char * 64),
    ]


class _Sigevent(_ctypes.Structure):
    _fields_ = [
        ("sigev_value", _Sigval),
        ("sigev_signo", _ctypes.c_int),
        ("sigev_notify", _ctypes.c_int),
        ("_sigev_un", _SigeventUnion),
    ]


class _Timespec(_ctypes.Structure):
    _fields_ = [("tv_sec", _ctypes.c_long), ("tv_nsec", _ctypes.c_long)]


class _Itimerspec(_ctypes.Structure):
    _fields_ = [("it_interval", _Timespec), ("it_value", _Timespec)]


_timer_t = _ctypes.c_void_p

_timer_create = _libc.timer_create
_timer_create.argtypes = (_ctypes.c_int, _ctypes.POINTER(_Sigevent), _ctypes.POINTER(_timer_t))
_timer_create.restype = _ctypes.c_int

_timer_settime = _libc.timer_settime
_timer_settime.argtypes = (
    _timer_t,
    _ctypes.c_int,
    _ctypes.POINTER(_Itimerspec),
    _ctypes.POINTER(_Itimerspec),
)
_timer_settime.restype = _ctypes.c_int

_timer_delete = _libc.timer_delete
_timer_delete.argtypes = (_timer_t,)
_timer_delete.restype = _ctypes.c_int


def _ensure_loop(loop: Optional[_asyncio.AbstractEventLoop]) -> _asyncio.AbstractEventLoop:
    if loop is not None:
        return loop
    try:
        return _asyncio.get_running_loop()
    except RuntimeError:
        return _asyncio.get_event_loop()


def _timestamp_to_spec(timestamp: float) -> _Itimerspec:
    fractional, integral = _math.modf(timestamp)
    nanoseconds = int(round(fractional * 1_000_000_000))
    seconds = int(integral)
    if nanoseconds >= 1_000_000_000:
        seconds += 1
        nanoseconds -= 1_000_000_000
    return _Itimerspec(
        it_interval=_Timespec(0, 0),
        it_value=_Timespec(seconds, nanoseconds),
    )


_contexts: Dict[int, "_TimerContext"] = {}


class _TimerContext:
    __slots__ = ("loop", "future", "timer_id", "_closed", "key")

    def __init__(self, loop: _asyncio.AbstractEventLoop, future: _asyncio.Future):
        self.loop = loop
        self.future = future
        self.timer_id = _timer_t()
        self._closed = False
        self.key = id(self)
        _contexts[self.key] = self

    def start(self, target_time: _datetime.datetime) -> None:
        sigevent = _Sigevent()
        sigevent.sigev_notify = _SIGEV_THREAD
        sigevent.sigev_signo = 0
        sigevent._sigev_un._sigev_thread.sigev_notify_function = _timer_callback
        sigevent._sigev_un._sigev_thread.sigev_notify_attributes = None
        sigevent.sigev_value.sival_ptr = _ctypes.c_void_p(self.key)

        timer_id = _timer_t()
        if _timer_create(_CLOCK_REALTIME, _ctypes.byref(sigevent), _ctypes.byref(timer_id)) != 0:
            err = _ctypes.get_errno()
            raise OSError(err, "Failed to create POSIX timer")
        self.timer_id = timer_id

        spec = _timestamp_to_spec(target_time.timestamp())
        if _timer_settime(timer_id, _TIMER_ABSTIME, _ctypes.byref(spec), None) != 0:
            err = _ctypes.get_errno()
            self.cleanup()
            raise OSError(err, "Failed to set POSIX timer")

    def _resolve(self) -> None:
        if self._closed:
            return
        if not self.future.done():
            self.future.set_result(None)
        self.cleanup()

    def _on_timer(self) -> None:
        if self._closed:
            return
        self.loop.call_soon_threadsafe(self._resolve)

    def cleanup(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self.timer_id and self.timer_id.value:
                _timer_delete(self.timer_id)
        finally:
            _contexts.pop(self.key, None)
            self.timer_id = _timer_t()


@_TimerCallback
def _timer_callback(sigval: _Sigval) -> None:  # pragma: no cover - executed in C thread
    key = int(sigval.sival_ptr)
    context = _contexts.get(key)
    if context is not None:
        context._on_timer()


def wait_until(
    target_time: _datetime.datetime,
    loop: Optional[_asyncio.AbstractEventLoop] = None,
) -> _asyncio.Future:
    """Return a future that resolves when ``target_time`` is reached."""

    loop = _ensure_loop(loop)
    future = loop.create_future()
    context = _TimerContext(loop, future)

    try:
        context.start(target_time)
    except Exception:
        context.cleanup()
        raise

    def _on_done(_fut: _asyncio.Future) -> None:
        context.cleanup()

    future.add_done_callback(_on_done)
    return future


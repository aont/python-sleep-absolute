"""macOS implementation backed by Grand Central Dispatch."""
from __future__ import annotations

from typing import Optional
import asyncio as _asyncio
import datetime as _datetime
import math as _math
import ctypes as _ctypes
import ctypes.util as _ctypes_util

__all__ = ["wait_until"]

_dispatch_lib_path = _ctypes_util.find_library("dispatch")
if _dispatch_lib_path is None:  # pragma: no cover - platform specific fallback
    _dispatch_lib_path = "/usr/lib/system/libdispatch.dylib"

_libdispatch = _ctypes.CDLL(_dispatch_lib_path, use_errno=True)


class _Timespec(_ctypes.Structure):
    _fields_ = [("tv_sec", _ctypes.c_long), ("tv_nsec", _ctypes.c_long)]


_dispatch_source_type_timer = _ctypes.c_void_p.in_dll(
    _libdispatch, "dispatch_source_type_timer"
)

_dispatch_function_t = _ctypes.CFUNCTYPE(None, _ctypes.c_void_p)

_dispatch_source_create = _libdispatch.dispatch_source_create
_dispatch_source_create.argtypes = (
    _ctypes.c_void_p,
    _ctypes.c_ulonglong,
    _ctypes.c_ulong,
    _ctypes.c_void_p,
)
_dispatch_source_create.restype = _ctypes.c_void_p

_dispatch_source_set_timer = _libdispatch.dispatch_source_set_timer
_dispatch_source_set_timer.argtypes = (
    _ctypes.c_void_p,
    _ctypes.c_uint64,
    _ctypes.c_uint64,
    _ctypes.c_uint64,
)
_dispatch_source_set_timer.restype = None

_dispatch_source_set_event_handler_f = _libdispatch.dispatch_source_set_event_handler_f
_dispatch_source_set_event_handler_f.argtypes = (_ctypes.c_void_p, _dispatch_function_t)
_dispatch_source_set_event_handler_f.restype = None

_dispatch_source_set_cancel_handler_f = _libdispatch.dispatch_source_set_cancel_handler_f
_dispatch_source_set_cancel_handler_f.argtypes = (_ctypes.c_void_p, _dispatch_function_t)
_dispatch_source_set_cancel_handler_f.restype = None

_dispatch_set_context = _libdispatch.dispatch_set_context
_dispatch_set_context.argtypes = (_ctypes.c_void_p, _ctypes.c_void_p)
_dispatch_set_context.restype = None

_dispatch_source_cancel = _libdispatch.dispatch_source_cancel
_dispatch_source_cancel.argtypes = (_ctypes.c_void_p,)
_dispatch_source_cancel.restype = None

_dispatch_release = _libdispatch.dispatch_release
_dispatch_release.argtypes = (_ctypes.c_void_p,)
_dispatch_release.restype = None

_dispatch_resume = _libdispatch.dispatch_resume
_dispatch_resume.argtypes = (_ctypes.c_void_p,)
_dispatch_resume.restype = None

_dispatch_walltime = _libdispatch.dispatch_walltime
_dispatch_walltime.argtypes = (_ctypes.POINTER(_Timespec), _ctypes.c_int64)
_dispatch_walltime.restype = _ctypes.c_uint64

_dispatch_get_global_queue = _libdispatch.dispatch_get_global_queue
_dispatch_get_global_queue.argtypes = (_ctypes.c_long, _ctypes.c_ulong)
_dispatch_get_global_queue.restype = _ctypes.c_void_p

_DISPATCH_TIME_FOREVER = _ctypes.c_uint64(0xFFFFFFFFFFFFFFFF).value


def _ensure_loop(loop: Optional[_asyncio.AbstractEventLoop]) -> _asyncio.AbstractEventLoop:
    if loop is not None:
        return loop
    try:
        return _asyncio.get_running_loop()
    except RuntimeError:
        return _asyncio.get_event_loop()


def _context_from_ptr(ctx: int) -> _TimerContext | None:
    if not ctx:
        return None
    void_p = _ctypes.c_void_p(ctx)
    py_obj = _ctypes.cast(void_p, _ctypes.POINTER(_ctypes.py_object))
    return py_obj.contents.value


class _TimerContext:
    __slots__ = (
        "loop",
        "future",
        "timer",
        "_cancelled",
        "_py_obj_ref",
        "_py_obj_ptr",
    )

    def __init__(
        self,
        loop: _asyncio.AbstractEventLoop,
        future: _asyncio.Future,
        timer: _ctypes.c_void_p,
    ) -> None:
        self.loop = loop
        self.future = future
        self.timer = timer
        self._cancelled = False
        self._py_obj_ref: Optional[_ctypes.py_object] = None
        self._py_obj_ptr: Optional[_ctypes.POINTER(_ctypes.py_object)] = None

    def as_context_ptr(self) -> _ctypes.c_void_p:
        if self._py_obj_ref is None or self._py_obj_ptr is None:
            self._py_obj_ref = _ctypes.py_object(self)
            self._py_obj_ptr = _ctypes.pointer(self._py_obj_ref)
        return _ctypes.cast(self._py_obj_ptr, _ctypes.c_void_p)

    def cancel_timer(self) -> None:
        if self.timer is None:
            return
        if self._cancelled:
            return
        self._cancelled = True
        _dispatch_source_cancel(self.timer)

    def release(self) -> None:
        if self.timer is not None:
            _dispatch_release(self.timer)
            self.timer = None
        self._py_obj_ref = None
        self._py_obj_ptr = None


def _event_handler(ctx: int) -> None:
    context = _context_from_ptr(ctx)
    if context is None:
        return
    future = context.future
    if future.done():
        context.cancel_timer()
        return

    def _set_result() -> None:
        if not future.done():
            future.set_result(None)

    context.loop.call_soon_threadsafe(_set_result)
    context.cancel_timer()


def _cancel_handler(ctx: int) -> None:
    context = _context_from_ptr(ctx)
    if context is None:
        return
    context.release()


_EVENT_HANDLER = _dispatch_function_t(_event_handler)
_CANCEL_HANDLER = _dispatch_function_t(_cancel_handler)


def _program_timer(timer: _ctypes.c_void_p, target_time: _datetime.datetime) -> None:
    timestamp = target_time.timestamp()
    fractional, integral = _math.modf(timestamp)
    nanoseconds = int(round(fractional * 1_000_000_000))
    seconds = int(integral)
    if nanoseconds >= 1_000_000_000:
        seconds += 1
        nanoseconds -= 1_000_000_000

    ts = _Timespec(seconds, nanoseconds)
    start_time = _dispatch_walltime(_ctypes.byref(ts), 0)
    _dispatch_source_set_timer(
        timer,
        start_time,
        _DISPATCH_TIME_FOREVER,
        _ctypes.c_uint64(1_000_000).value,
    )


def wait_until(
    target_time: _datetime.datetime,
    loop: Optional[_asyncio.AbstractEventLoop] = None,
) -> _asyncio.Future:
    """Return a future that resolves when ``target_time`` is reached."""

    loop = _ensure_loop(loop)
    future = loop.create_future()

    queue = _dispatch_get_global_queue(0, 0)
    if not queue:  # pragma: no cover - platform specific failure
        raise OSError("Failed to obtain dispatch queue")

    timer = _dispatch_source_create(_dispatch_source_type_timer, 0, 0, queue)
    if not timer:  # pragma: no cover - platform specific failure
        raise OSError("Failed to create dispatch timer")

    context = _TimerContext(loop, future, timer)
    context_ptr = context.as_context_ptr()

    _dispatch_set_context(timer, context_ptr)
    _dispatch_source_set_event_handler_f(timer, _EVENT_HANDLER)
    _dispatch_source_set_cancel_handler_f(timer, _CANCEL_HANDLER)

    _program_timer(timer, target_time)
    _dispatch_resume(timer)

    def _cleanup(_fut: _asyncio.Future) -> None:
        context.cancel_timer()

    future.add_done_callback(_cleanup)
    return future


import asyncio as _asyncio
import datetime as _datetime
import sys as _sys
import math as _math

# if sys.platform.startswith("linux"):
import ctypes as _ctypes
import os as _os
# import time as _time

_libc = _ctypes.CDLL("libc.so.6", use_errno=True)
_CLOCK_REALTIME = 0
# _TIMER_ABSTIME = 1

_TFD_NONBLOCK = 0o4000
_TFD_CLOEXEC = 0o2000000

_timerfd_create = _libc.timerfd_create
_timerfd_create.argtypes = [_ctypes.c_int, _ctypes.c_int]
_timerfd_create.restype = _ctypes.c_int

_timerfd_settime = _libc.timerfd_settime
_timerfd_settime.argtypes = [_ctypes.c_int, _ctypes.c_int, _ctypes.c_void_p, _ctypes.POINTER(_ctypes.c_longlong)]
_timerfd_settime.restype = _ctypes.c_int

class _timespec(_ctypes.Structure):
    _fields_ = [("tv_sec", _ctypes.c_long), ("tv_nsec", _ctypes.c_long)]

class _itimerspec(_ctypes.Structure):
    _fields_ = [("it_interval", _timespec), ("it_value", _timespec)]

def _create_timerfd():
    fd = _timerfd_create(_CLOCK_REALTIME, _TFD_NONBLOCK | _TFD_CLOEXEC)
    if fd == -1:
        raise OSError("Failed to create timerfd")
    return fd

def _set_timerfd_absolute(fd, target_time: _datetime.datetime):
    target_timestamp = target_time.timestamp()
    target_timestamp_modf = _math.modf(target_timestamp)
    nsec = int(target_timestamp_modf[0] * 1e9)
    sec = int(target_timestamp_modf[1])
    new_value = _itimerspec(it_interval=_timespec(0, 0), it_value=_timespec(sec, nsec))
    if _timerfd_settime(fd, 1, _ctypes.byref(new_value), None) != 0:
        raise OSError("Failed to set timerfd")

class Sleeper:

    def __init__(self):
        self._fd = None
        # self._cancelled = False
        self._event = _asyncio.Event()
        self._event_wait_fut = _asyncio.Future()
        self._loop = None

    async def _wait_timerfd(self, fd, no_cancel_error):
        self._loop = _asyncio.get_running_loop()
        self._event.clear()
        self._loop.add_reader(fd, self._event.set)
        self._event_wait_fut = _asyncio.ensure_future(self._event.wait())
        if no_cancel_error:
            try:
                await self._event_wait_fut
            except _asyncio.CancelledError:
                self._event_wait_fut = None
                return
        else:
            await self._event_wait_fut
        self._event_wait_fut = None
        self._loop.remove_reader(fd)
        _os.close(fd)

    async def wait_until(self, target_time: _datetime.datetime, no_cancel_error: bool = False):
        self._fd = _create_timerfd()
        _set_timerfd_absolute(self._fd, target_time)
        await self._wait_timerfd(self._fd, no_cancel_error)
        self._fd = None
        
    async def cancel(self):
        self._event.set()
        if self._fd is not None:
            self._loop.remove_reader(self._fd)
            _os.close(self._fd)
            self._fd = None
        if self._event_wait_fut is not None:
            self._event_wait_fut.cancel()


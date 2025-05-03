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

def _create_timerfd_absolute_time(target_time: _datetime.datetime):
    fd = _create_timerfd()
    target_timestamp = target_time.timestamp()
    target_timestamp_modf = _math.modf(target_timestamp)
    nsec = int(target_timestamp_modf[0] * 1e9)
    sec = int(target_timestamp_modf[1])
    new_value = _itimerspec(it_interval=_timespec(0, 0), it_value=_timespec(sec, nsec))
    if _timerfd_settime(fd, 1, _ctypes.byref(new_value), None) != 0:
        raise OSError("Failed to set timerfd")
    return fd

def wait_until(target_time: _datetime.datetime, loop=None) -> _asyncio.Future:
    if loop is None: loop = _asyncio.get_event_loop()
    fd = _create_timerfd_absolute_time(target_time)
    loop = _asyncio.get_running_loop()
    fut = _asyncio.Future()

    def on_ready():
        if not fut.done():
            fut.set_result(None)
        loop.remove_reader(fd)
        _os.close(fd)

    loop.add_reader(fd, on_ready)

    def cancel_callback(fut: _asyncio.Future):
        if fut.cancelled():
            # _sys.stderr.write("debug: cancel_callback\n")
            loop.remove_reader(fd)
            _os.close(fd)

    fut.add_done_callback(cancel_callback)
    return fut


async def _main():
    import asyncio
    import datetime
    import sys

    target = datetime.datetime.now() + datetime.timedelta(seconds=2)
    sys.stderr.write(f"Waiting until {target} using 'timerfd' ...\n")

    wait_until_fut = asyncio.ensure_future(wait_until(target))

    asyncio.get_event_loop().call_later(1, wait_until_fut.cancel)

    await wait_until_fut
    sys.stderr.write(f"Woke up {datetime.datetime.now()}\n")

if __name__ == "__main__":
    import asyncio
    asyncio.run(_main())
import asyncio as _asyncio
import datetime as _datetime
import sys as _sys

import ctypes as _ctypes
from ctypes import wintypes as _wintypes

_kernel32 = _ctypes.WinDLL("kernel32", use_last_error=True)

_CreateWaitableTimerW = _kernel32.CreateWaitableTimerW
_CreateWaitableTimerW.argtypes = [_ctypes.c_void_p, _wintypes.BOOL, _wintypes.LPCWSTR]
_CreateWaitableTimerW.restype = _wintypes.HANDLE

_SetWaitableTimer = _kernel32.SetWaitableTimer
_SetWaitableTimer.argtypes = [_wintypes.HANDLE, _ctypes.POINTER(_ctypes.c_longlong), _wintypes.LONG, _ctypes.c_void_p, _ctypes.c_void_p, _wintypes.BOOL]
_SetWaitableTimer.restype = _wintypes.BOOL

_WaitForSingleObject = _kernel32.WaitForSingleObject
_WaitForSingleObject.argtypes = [_wintypes.HANDLE, _wintypes.DWORD]
_WaitForSingleObject.restype = _wintypes.DWORD

_CloseHandle = _kernel32.CloseHandle
_CloseHandle.argtypes = [_wintypes.HANDLE]
_CloseHandle.restype = _wintypes.BOOL

def wait_until(target_time: _datetime.datetime, loop=None) -> _asyncio.Future:
    # ここでは pywin32 を使わず ctypes により Waitable Timer を利用します。
    if loop is None:
        loop = _asyncio.get_running_loop()
    proactor: _asyncio.windows_events.IocpProactor = loop._proactor
    # ターゲット時刻をFILETIME形式（100ns単位、1601/1/1基準）に変換
    utc_target = target_time.astimezone(_datetime.timezone.utc)
    epoch_start = _datetime.datetime(1601, 1, 1, tzinfo=_datetime.timezone.utc)
    due_time_intervals = int((utc_target - epoch_start).total_seconds() * 1e7)
    due_time = _ctypes.c_longlong(due_time_intervals)

    timer = _CreateWaitableTimerW(None, True, None)
    # _sys.stderr.write(f"[debug] {timer=}\n")
    if not timer:
        raise OSError(_ctypes.get_last_error(), "Failed to create waitable timer")

    if not _SetWaitableTimer(timer, _ctypes.byref(due_time), 0, None, None, False):
        err = _ctypes.get_last_error()
        _CloseHandle(timer)
        raise OSError(err, "Failed to set waitable timer")

    fut = proactor.wait_for_handle(timer, None)
    def cancel_callback(fut: _asyncio.Future):
        if fut.cancelled():
            # _sys.stderr.write("debug: cancel_callback\n")
            # proactor.remove_waiter(timer)
            _CloseHandle(timer)
    fut.add_done_callback(cancel_callback)
    return fut

# --- デモ用 main() ---
async def _main():
    # 利用例: 現在時刻から5秒後をターゲット
    target = _datetime.datetime.now() + _datetime.timedelta(seconds=2)

    print(f"Waiting until {target} using 'win32event' (ctypes) ...")
    fut = _asyncio.ensure_future(wait_until(target))
    _asyncio.get_event_loop().call_later(1, fut.cancel)
    await fut
    print("Woke up (win32event)!")

if __name__ == "__main__":
    _asyncio.run(_main())

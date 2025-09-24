"""Async utilities to wait until an absolute timestamp.

The :func:`wait_until` helper selects the optimal implementation for the
current platform.  On Linux it uses ``timerfd`` via :mod:`ctypes`, while on
Windows it relies on waitable timers.  Other platforms are currently not
supported.
"""
from __future__ import annotations

from typing import Optional
import asyncio as _asyncio
import datetime as _datetime
import sys as _sys

__all__ = ["wait_until", "__version__"]
__version__ = "0.1.0"

if _sys.platform.startswith("linux"):
    from . import _linux as _impl
elif _sys.platform.startswith(("win32", "cygwin")):
    from . import _windows as _impl  # pragma: no cover - platform specific
else:  # pragma: no cover - platform specific
    _impl = None


def wait_until(
    target_time: _datetime.datetime,
    loop: Optional[_asyncio.AbstractEventLoop] = None,
) -> _asyncio.Future:
    """Return a future that resolves once ``target_time`` is reached.

    Args:
        target_time: Absolute point in time when the future should complete.
        loop: Event loop instance.  When omitted the current running loop is
            used.  If no loop is running an attempt is made to fetch the global
            default loop.

    Returns:
        ``asyncio.Future`` that resolves to :data:`None` once ``target_time`` is
        reached.  The future can be cancelled to stop waiting earlier.

    Raises:
        NotImplementedError: if the current platform is unsupported.
    """
    if _impl is None:
        raise NotImplementedError("sleep_absolute.wait_until is not available on this platform")
    return _impl.wait_until(target_time, loop=loop)


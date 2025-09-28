import asyncio
import datetime
import importlib
import unittest

try:
    from sleep_absolute import wait_until
except NotImplementedError:  # pragma: no cover - unsupported platform
    wait_until = None  # type: ignore[assignment]

try:
    _posix_impl = importlib.import_module("sleep_absolute._timer_create")
except (ImportError, OSError):  # pragma: no cover - platform specific
    _posix_impl = None  # type: ignore[assignment]


@unittest.skipIf(wait_until is None, "sleep_absolute is unsupported on this platform")
class WaitUntilTests(unittest.IsolatedAsyncioTestCase):
    async def test_waits_until_target_time(self) -> None:
        target = datetime.datetime.now() + datetime.timedelta(milliseconds=100)
        before = datetime.datetime.now()
        await wait_until(target)
        after = datetime.datetime.now()
        self.assertGreaterEqual(after, target)
        # Ensure we did not wake up immediately.
        self.assertGreaterEqual((after - before).total_seconds(), 0.09)

    async def test_cancellation(self) -> None:
        target = datetime.datetime.now() + datetime.timedelta(seconds=1)
        fut = wait_until(target)
        self.assertFalse(fut.done())
        fut.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await fut
        self.assertTrue(fut.cancelled())


@unittest.skipIf(_posix_impl is None, "timer_create implementation unavailable")
class TimerCreateTests(unittest.IsolatedAsyncioTestCase):
    async def test_waits_until_target_time(self) -> None:
        target = datetime.datetime.now() + datetime.timedelta(milliseconds=100)
        before = datetime.datetime.now()
        await _posix_impl.wait_until(target)
        after = datetime.datetime.now()
        self.assertGreaterEqual(after, target)
        self.assertGreaterEqual((after - before).total_seconds(), 0.09)

    async def test_cancellation(self) -> None:
        target = datetime.datetime.now() + datetime.timedelta(seconds=1)
        fut = _posix_impl.wait_until(target)
        self.assertFalse(fut.done())
        fut.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await fut
        self.assertTrue(fut.cancelled())


if __name__ == "__main__":
    unittest.main()

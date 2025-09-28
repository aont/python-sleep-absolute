# sleep-absolute

Asyncio helper that waits until an absolute timestamp without blocking the event
loop.  Linux uses the native `timerfd` API while Windows relies on waitable
timers exposed through `ctypes`.

## Installation

The project is published as a source distribution and can be installed directly
from GitHub:

```bash
pip install git+https://github.com/aont/python-sleep-absolute.git
```

Replace `<your-account>` with the name of the GitHub organisation or user that
hosts the repository.

## Python compatibility

The package supports Python 3.9 and newer.  The test-suite is regularly run on
CPython 3.9 through 3.12 to ensure continued compatibility.

## Running the tests

When working on the project locally, set ``PYTHONPATH`` so the package can be
imported from the ``src`` layout:

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

## Usage

```python
import asyncio
import datetime

from sleep_absolute import wait_until

async def main() -> None:
    target = datetime.datetime.now() + datetime.timedelta(seconds=5)
    await wait_until(target)
    print("Reached target time")

asyncio.run(main())
```

The returned future may be cancelled to stop waiting earlier.

## Supported platforms

* Linux (`timerfd` based implementation)
* Windows (waitable timer implementation)

Other platforms currently raise :class:`NotImplementedError`.

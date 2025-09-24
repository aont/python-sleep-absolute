# sleep-absolute

Asyncio helper that waits until an absolute timestamp without blocking the event
loop.  Linux uses the native `timerfd` API while Windows relies on waitable
timers exposed through `ctypes`.

## Installation

The project is published as a source distribution and can be installed directly
from GitHub:

```bash
pip install git+https://github.com/<your-account>/python-sleep-absolute.git
```

Replace `<your-account>` with the name of the GitHub organisation or user that
hosts the repository.

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

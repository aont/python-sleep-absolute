import asyncio
import datetime
import sys
import timerfd

async def main():
    target = datetime.datetime.now() + datetime.timedelta(seconds=5)
    sys.stderr.write(f"Waiting until {target} using 'timerfd' ...\n")

    sleeper = timerfd.Sleeper()

    loop = asyncio.get_running_loop()
    loop.call_later(1.0, lambda: loop.create_task(sleeper.cancel()))

    # await sleeper.wait_until(target, no_cancel_error=True)
    await sleeper.wait_until(target)
    sys.stderr.write(f"Woke up {datetime.datetime.now()}\n")


if __name__ == "__main__":
    asyncio.run(main())
    # print(timerfd._os)

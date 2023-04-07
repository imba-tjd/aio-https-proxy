import asyncio


class TimeoutStreamReader(asyncio.StreamReader):
    timeout: float

    async def readline(self):
        async with asyncio.timeout(self.timeout):
            return await super().readline()

    async def read(self, n=-1):
        async with asyncio.timeout(self.timeout):
            return await super().read(n)

    async def readuntil(self, seperator: bytes):
        async with asyncio.timeout(self.timeout):
            return await super().readuntil(seperator)

    @staticmethod
    def from_super(reader: asyncio.StreamReader, timeout: float = 3) -> 'TimeoutStreamReader':
        reader.__class__ = TimeoutStreamReader
        reader.timeout = timeout  # type:ignore
        return reader  # type: ignore


class TimeoutStreamWriter(asyncio.StreamWriter):
    timeout: float

    async def drain(self):
        async with asyncio.timeout(self.timeout):
            return await super().drain()

    @staticmethod
    def from_super(writer: asyncio.StreamWriter, timeout: float = 15) -> 'TimeoutStreamWriter':
        writer.__class__ = TimeoutStreamWriter
        writer.timeout = timeout  # type:ignore
        return writer  # type: ignore


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    while True:
        data = await reader.read(256)
        await asyncio.sleep(0)

        if writer.is_closing():
            return

        if data:
            writer.write(data)
        elif reader.at_eof():
            writer.close()
            await writer.wait_closed()
            return
        else:
            await writer.drain()

class AtomicInt:
    def __init__(self, value: int = 0):
        self.value = value

    async def incr(self):
        async with asyncio.Lock():
            self.value += 1
            return self.value

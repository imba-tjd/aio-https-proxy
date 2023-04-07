import asyncio
import socket
import logging
import asyncio_extra

logger = logging.getLogger(__name__)

SerialNum = asyncio_extra.AtomicInt()


class ClientError(Exception):
    @property
    def msg(self) -> bytes:
        assert len(self.args) >= 1
        if isinstance(self.args[0], bytes):
            return self.args[0]
        elif len(self.args) == 1:
            return b''
        elif isinstance(self.args[1], bytes):
            return self.args[1]
        else:
            assert False

    @property
    def code(self) -> int:
        assert len(self.args) >= 1
        assert isinstance(self.args[0], int)
        return self.args[0]

    @property
    def format_msg(self) -> bytes:
        if isinstance(self.args[0], bytes):
            return b'HTTP/1.1 400 Bad Request\r\n\r\n%s\r\n\r\n' % self.msg
        elif isinstance(self.args[0], int):
            return b'HTTP/1.1 %d %s\r\n\r\n%s\r\n\r\n' % (self.code, self._msg_map[self.code], self.msg)
        else:
            assert False

    _msg_map = {
        400: b'Bad Request',
        403: b'Forbidden',
        500: b'Internal Server Error',
        502: b'Bad Gateway',
        504: b'Gateway Timeout',
    }


class UnsupportedError(ClientError):
    pass


def parse_hello(hello: bytes):
    if not hello:
        raise UnsupportedError(b'hello is empty')

    parts = hello.split(b' ')
    if len(parts) != 3 or parts[0] != b'CONNECT':
        raise UnsupportedError(b'only support CONNECT')

    target = parts[1].split(b':')
    if len(target) != 2:
        raise UnsupportedError(b'invalid target')

    host, port = target[0].decode(), int(target[1])

    if port == 80:
        raise UnsupportedError(b'unsupported port 80')

    return host, port


def get_client_ip(headers: dict[bytes, bytes], writer: asyncio.StreamWriter):
    if b'x-forwarded-for' in headers:
        ip = headers[b'x-forwarded-for'].split(b',')[0]
    elif b'x-real-ip' in headers:
        ip = headers[b'x-real-ip']
    else:
        ip = writer.get_extra_info('peername')[0]  # perrname结果为(ip,port)
    return str(ip)


async def main_handler(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter, sno: int):
    connect_hello = await client_reader.readline()

    host, port = parse_hello(connect_hello)

    headers_raw = await client_reader.readuntil(b'\r\n\r\n')

    headers_raw = headers_raw.removesuffix(b'\r\n\r\n')
    headers = dict(tuple(line.split(b': ')) for line in headers_raw.split(b'\r\n'))

    cip = get_client_ip(headers, client_writer)
    logger.info('\x1B[32m%3d: %s CONNECT %s%s\x1B[m', sno, cip, host, (':%d' % port if port != 443 else ''))

    try:
        async with asyncio.timeout(3):
            upstream_reader, upstream_writer = await asyncio.open_connection(host, port)
            client_writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            await client_writer.drain()
    except asyncio.TimeoutError:
        raise ClientError(504)
    except socket.gaierror:
        raise ClientError(502)
    except ConnectionError:  # 此处应该仅为客户端出错
        client_writer.transport.abort()
        logger.debug('\x1B[31m%3d: ConnectionError\x1B[m', sno, stack_info=True)
        if locals()['upstream_writer']:
            logger.debug('\x1B[31m%3d: CloseUpstream\x1B[m', sno)
            upstream_writer.close()  # type: ignore
        return
    except:
        logger.exception('\x1B[31m%3d: open_connection failed\x1B[m', sno)
        raise ClientError(500)

    # upstream_reader = asyncio_extra.TimeoutStreamReader.from_super(upstream_reader, 15)
    # upstream_writer = asyncio_extra.TimeoutStreamWriter.from_super(upstream_writer, 15)
    async with asyncio.TaskGroup() as tg:
        try:
            tg.create_task(asyncio_extra.pipe(client_reader, upstream_writer))
            tg.create_task(asyncio_extra.pipe(upstream_reader, client_writer))
        except ConnectionError:
            client_writer.transport.abort()
        except asyncio.TimeoutError:
            client_writer.transport.abort()
        except:
            logger.exception('\x1B[31m%3d: Exception during connection\x1B[m', sno)
            client_writer.transport.abort()


async def handler(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter):
    sno = await SerialNum.incr()
    # client_reader = asyncio_extra.TimeoutStreamReader.from_super(client_reader)
    # client_writer = asyncio_extra.TimeoutStreamWriter.from_super(client_writer, 15)

    try:
        await main_handler(client_reader, client_writer, sno)
    except ClientError as e:
        if isinstance(e, UnsupportedError):
            logger.debug('\x1B[33m%3d: %s\x1B[m', sno, e.msg)

        if client_writer.is_closing():
            return
        client_writer.write(e.format_msg)
        client_writer.close()
        await client_writer.wait_closed()
    except asyncio.TimeoutError:
        client_writer.transport.abort()
    except:
        client_writer.transport.abort()
        logger.exception('\x1B[31m%3d: Exception during handler\x1B[m', sno)
    finally:
        logger.info('%3d: Connection ended', sno)


async def server(port: int = 1080):
    server = await asyncio.start_server(handler, '0.0.0.0', port)
    logger.info('Listening ' + str(server.sockets[0].getsockname()))

    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    log_format = '\x1B[36m%(asctime)s\x1B[m %(levelname)s: %(message)s'
    logging.basicConfig(format=log_format, level=logging.DEBUG)
    try:
        asyncio.run(server())
    except KeyboardInterrupt:
        pass

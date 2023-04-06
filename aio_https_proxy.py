import asyncio
import socket
import logging
import asyncio_extra

logger = logging.getLogger(__name__)

sno = 0  # serial number


async def atomic_incr_sno():
    global sno
    async with asyncio.Lock():
        sno += 1


class ClientError(Exception):
    @property
    def msg(self) -> bytes:
        assert len(self.args) <= 1
        if len(self.args) == 0:
            return b''

        assert isinstance(self.args[0], bytes)
        return self.args[0]


class UnsupportedError(ClientError):
    pass


def parse_hello(hello: bytes):
    if not hello:
        raise UnsupportedError('hello is empty')

    parts = hello.split(b' ')
    if len(parts) != 3 or parts[0] != b'CONNECT':
        raise UnsupportedError('only support CONNECT')

    target = parts[1].split(b':')
    if len(target) != 2:
        raise UnsupportedError('invalid target')

    host, port = target[0].decode(), int(target[1])

    if port == 80:
        raise UnsupportedError('unsupported port 80')

    return host, port


def get_client_ip(headers: dict[bytes, bytes], writer: asyncio.StreamWriter):
    if b'x-forwarded-for' in headers:
        ip = headers[b'x-forwarded-for'].split(b',')[0]
    elif b'x-real-ip' in headers:
        ip = headers[b'x-real-ip']
    else:
        ip = writer.get_extra_info('peername')[0]  # perrname结果为(ip,port)
    return str(ip)


async def main_handler(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter):
    connect_hello = await client_reader.readline()

    host, port = parse_hello(connect_hello)

    headers_raw = await client_reader.readuntil(b'\r\n\r\n')

    headers_raw = headers_raw.removesuffix(b'\r\n\r\n')
    headers = dict(tuple(line.split(b': ')) for line in headers_raw.split(b'\r\n'))

    cip = get_client_ip(headers, client_writer)
    logger.info('\x1B[32m%d: %s CONNECT %s%s\x1B[m', sno, cip, host, (':%d' % port if port != 443 else ''))

    try:
        async with asyncio.timeout(3):
            upstream_reader, upstream_writer = await asyncio.open_connection(host, port)
            client_writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            await client_writer.drain()
    except asyncio.TimeoutError:
        client_writer.write(b'HTTP/1.1 504 Gateway timeout\r\n\r\n')
        client_writer.close()
        return
    except socket.gaierror:
        client_writer.write(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')
        client_writer.close()
        return
    except ConnectionError:  # 此处应该仅为客户端出错
        client_writer.transport.abort()
        if locals()['upstream_writer']:
            upstream_writer.close()  # type: ignore
        return
    except:
        logger.exception('\x1B[31m%d: open_connection failed\x1B[m', sno)
        client_writer.write(b'HTTP/1.1 500 Internal Server Error\r\n\r\n')
        client_writer.close()
        return

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
            logger.exception('\x1B[31m%d: Exception during connection\x1B[m', sno)
            client_writer.transport.abort()


async def handler(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter):
    await atomic_incr_sno()
    # client_reader = asyncio_extra.TimeoutStreamReader.from_super(client_reader)
    # client_writer = asyncio_extra.TimeoutStreamWriter.from_super(client_writer, 15)

    try:
        await main_handler(client_reader, client_writer)
    except ClientError as e:
        if client_writer.is_closing():
            return
        client_writer.write(b'HTTP/1.1 400 Bad Request\r\n\r\n')  # TODO: if DEBUG，输出e.msg
        client_writer.close()
    except asyncio.TimeoutError:
        client_writer.transport.abort()
    except:
        logger.exception('\x1B[31m%d: Exception during handler\x1B[m', sno)


async def server(port: int = 1080):
    server = await asyncio.start_server(handler, '0.0.0.0', port)
    logger.info('Listening ' + str(server.sockets[0].getsockname()))
    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    log_format = '\x1B[36m%(asctime)s %(levelname)s\x1B[m: %(message)s'
    logging.basicConfig(format=log_format, level=logging.INFO)
    asyncio.run(server())

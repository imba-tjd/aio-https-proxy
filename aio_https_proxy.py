import asyncio
import socket
import logging
import sys
from itertools import count
from functools import wraps


logger = logging.getLogger(__name__)
SerialNum = count()


class Utils:
    @staticmethod
    def timeout_patch(f, timeout: float):
        @wraps(f)
        async def wrapper(*args, **kw):
            async with asyncio.timeout(timeout):
                return await f(*args, **kw)
        return wrapper

    @staticmethod
    def reader_timeout_patch(r: asyncio.StreamReader, timeout = 15.0):
        r.read = Utils.timeout_patch(r.read, timeout)
        r.readline = Utils.timeout_patch(r.readline, timeout)
        r.readexactly = Utils.timeout_patch(r.readexactly, timeout)
        r.readuntil = Utils.timeout_patch(r.readuntil, timeout)

    @staticmethod
    def writer_timeout_patch(w: asyncio.StreamWriter, timeout = 15.0):
        w.drain = Utils.timeout_patch(w.drain, timeout)
        w.wait_closed = Utils.timeout_patch(w.wait_closed, timeout)

    @staticmethod
    async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        '''invariant: w is available. Deal with r's data and closing.'''
        while not writer.is_closing():
            data = await reader.read(512)

            if data:
                writer.write(data)
                await writer.drain()
            elif reader.at_eof():
                writer.close()
                await writer.wait_closed()
            else:
                assert False

class ResetClientError(Exception):
    '''abort the connection. not send msg to client'''
    pass

class ClientError(Exception):
    '''send error msg to client. The arg can be (int, bytes) or bytes'''
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
            self.args[0:1] = (400, self.args[0])
        return b'HTTP/1.1 %d %s\r\nConnection:Close\r\n\r\n%s\r\n\r\n' % (self.code, self._msg_map[self.code], self.msg)

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


async def connect_upstream(host, port, sno: int):
    try:
        async with asyncio.timeout(3):
            ur, uw = await asyncio.open_connection(host, port)
    except TimeoutError:
        raise ClientError(504)
    except socket.gaierror:
        raise ClientError(502)
    except:
        logger.exception('\x1B[31m%2d| connect_upstream failed\x1B[m', sno)
        raise ClientError(500)

    return ur, uw


async def determine_target(cr: asyncio.StreamReader, sno: int):
    try:
        async with asyncio.timeout(3):
            connect_hello = await cr.readline()
    except TimeoutError as e:
        raise ResetClientError(e)


    host, port = parse_hello(connect_hello)

    try:
        headers = (await cr.readuntil(b'\r\n\r\n')).removesuffix(b'\r\n\r\n')
    except TimeoutError | LimitOverrunError | IncompleteReadError as e:
        raise ResetClientError(e)

    # headers = dict(tuple(line.split(b': ', maxsplit=1)) for line in headers_raw.split(b'\r\n'))
    logger.debug('%3d| headers=%s', sno, headers)

    return host, port


async def handler(cr: asyncio.StreamReader, cw: asyncio.StreamWriter):
    sno = next(SerialNum)

    try:
        host, port = await determine_target(cr, sno)

        cip = cw.get_extra_info('peername')[0]
        logger.info('\x1B[32m%3d| %s CONNECT to %s%s\x1B[m', sno, cip, host, (f':{port}' if port != 443 else ''))

        ur, uw = await connect_upstream(host, port, sno)

        try:
            cw.write(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            await cw.drain()

            async with asyncio.TaskGroup() as tg:
                tg.create_task(Utils.pipe(cr, uw))
                tg.create_task(Utils.pipe(ur, cw))
        except Exception as e:
            logger.exception('\x1B[31m%2d| Exception during connection\x1B[m', sno)
            uw.transport.abort()
            raise ResetClientError(e)
        finally:
            uw.close()

    except ClientError as e:
        if isinstance(e, UnsupportedError):
            logger.debug('\x1B[33m%3d| %s\x1B[m', sno, e.msg)

        if cw.is_closing(): return
        try: cw.write(e.format_msg)
        except ConnectionResetError: pass
    except ResetClientError:
        cw.transport.abort()
    except:
        logger.exception('\x1B[31m%2d| Exception during handler\x1B[m', sno)
    finally:
        cw.close()
        logger.info('%3d| Connection ended', sno)


async def server(port):
    server = await asyncio.start_server(handler, port=port)
    logger.info('   Listening on ' + str(server.sockets[0].getsockname()[:2]))

    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    log_format = '\x1B[36m%(asctime)s\x1B[m %(levelname)s: %(message)s'
    logging.basicConfig(format=log_format, level=logging.INFO)

    port = 1080 if len(sys.argv) == 1 else int(sys.argv[1])

    try:
        asyncio.run(server(port))
    except KeyboardInterrupt:
        pass


    # except ConnectionError:  # 此处应该仅为客户端出错
    #     cw.transport.abort()
    #     logger.debug('\x1B[31m%3d| ConnectionError\x1B[m', sno, stack_info=True)
    #     if locals()['uw']:
    #         logger.debug('\x1B[31m%3d| CloseUpstream\x1B[m', sno)
    #         uw.close()  # type: ignore
    #     return

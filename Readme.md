# ASYNCIO HTTPS PROXY

A simple proxy server that supports and only supports HTTP CONNECT.

This is only a POC. Tested that `curl https://example.com -x 127.1` works. So the happy path is OK. However it has lots of Unhandled corner case.

## Thoughts for now

1. 双方正常结束。在pipe中处理了。
2. 上游出错，客户端可以写入。则将出错信息返回给客户端。关闭双方连接。
3. 客户端出错。关闭上游连接。
4. 对于长时间空闲而关闭的连接，应忽略。
5. 不应把upstream的连接嵌套在client中。

## Learnt

* If this is behind a reverse proxy, that proxy must be on L4, which make this basically useless. This is because the proxy acts both as server and client. A L7 reverse proxy won't forward CONNECT verb to the backend.

### IDN why

* Browser sometimes sends nothing, which triggers *hello is empty*. Maybe it's a kind of keepalive
* TimeoutStreamReader and Writer breaks things, ~~so does writer.write_eof() in pipe~~

## Won't fix

* Proxy-Authorization
* Deal with malicious client

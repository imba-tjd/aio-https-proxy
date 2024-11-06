# ASYNCIO HTTPS PROXY

A simple proxy server that supports and only supports HTTP CONNECT.

Usage: `python -m aio_https_proxy [port]`.

This is only a POC. Tested that `curl https://example.com -x 127.1` works.

There is no client implementaion in this code. You need to use existing program that supports CONNECT. For example curl and browser.

## Learnt

* If this is behind a reverse proxy, that proxy must be on L4, which make this basically useless. This is because the proxy acts both as server and client. A L7 reverse proxy won't forward CONNECT verb to the backend. Besides, after CONNECT, the client will start TLS session to upstream, and the data is not HTTP at all. The L7 proxy won't able to determine which backend to delegate to.
* workflow
  1. 若双方正常结束。在pipe中处理了。
  2. 尚未建立连接时的出错，应返回出错消息给客户端。包括客户端任何错误的协议内容、连接上游失败。
  3. 若已经建立了连接，不能返回错误信息给客户端，因为客户端已经“切换协议”了。只能abort。
  4. 难以添加超时逻辑。因为TCP是长连接的，一轮HTTP收发完了，连接会保留，阻塞在read()。要么只能将超时时间设置在分钟级别。
  5. 客户端和上游有任何一方断开连接，能够使得双方都断开，而不必处理 客户端和代理未断开、代理重连上游

### IDN why

* ~~Browser sometimes sends nothing, which triggers *hello is empty*~~

## Won't fix

* Proxy-Authorization
* Deal with malicious client

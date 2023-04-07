# AIO HTTPS PROXY

A proxy server that supports and only supports HTTP CONNECT.

Project State: Alpha. Tested that `curl https://example.com -x 127.0.0.1` works.

## Learnt

* If this is behind a reverse proxy, that proxy must be on L4, which make this basically useless

### IDN why

* Browser sometimes sends nothing, which triggers *hello is empty*
* TimeoutStreamReader and Writer breaks things, so does writer.write_eof() in pipe

## TODO

* 加密：Proxy-Authorization: basic base64编码的user:pass。不满足时返回407 Proxy Authentication Required
* 处理客户端慢连接攻击

## 其他人的项目

* https://github.com/mmatczuk/go-http-tunnel
* https://github.com/jpillora/chisel

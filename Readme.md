# AIO HTTPS PROXY

A proxy server that supports and only supports HTTP CONNECT.

Current State: Alpha

## TODO

* 加密：Proxy-Authorization: basic base64编码的user:pass。不满足时返回407 Proxy Authentication Required
* 处理客户端慢连接攻击

## 其他人的项目

* https://github.com/mmatczuk/go-http-tunnel
* https://github.com/jpillora/chisel

import gzip
import socket
import ssl
import time
from typing import BinaryIO


class URL:
    ALLOW_LIST = ["http", "https", "file", "data", "view-source"]
    SOCKET_CACHE: dict[
        tuple[str, int], tuple[ssl.SSLSocket | socket.socket, float]
    ] = {}

    def __init__(self, url: str) -> None:
        self.view_source: bool = False
        self.scheme: str = ""
        self.host: str = ""
        self.port: int | None = None
        self.path: str = ""

        if url.startswith("view-source:"):
            self.view_source = True
            url = url[len("view-source:") :]

        if url.startswith("data:"):
            self.scheme = "data"
            self.path = url[len("data:") :]
            return

        self.scheme, url = url.split("://", 1)
        assert self.scheme in self.ALLOW_LIST

        if self.scheme == "file":
            self.path = "/" + url
            return

        if "/" not in url:
            url = url + "/"
        self.host, url = url.split("/", 1)
        self.path = "/" + url

        if self.scheme == "http":
            self.port = 80
        elif self.scheme == "https":
            self.port = 443

        if ":" in self.host:
            self.host, port = self.host.split(":", 1)
            self.port = int(port)

    @staticmethod
    def read_chunked(response: BinaryIO) -> bytes:
        body = b""
        while True:
            size_line = response.readline()
            if not size_line:
                break  # connection closed unexpectedly
            # Size is hex; ignore any chunk extensions after ';'.
            size = int(size_line.split(b";")[0].strip(), 16)
            if size == 0:
                # Discard trailer headers up to the blank line.
                while True:
                    trailer = response.readline()
                    if trailer in (b"\r\n", b"\n", b""):
                        break
                break
            body += response.read(size)
            response.readline()  # discard the CRLF after the chunk data
        return body

    def request(self, max_redirects: int = 10) -> str:
        if self.scheme == "file":
            with open(self.path, "r", encoding="utf-8") as f:
                return f.read()

        if self.scheme == "data":
            _, content = self.path.split(",", 1)
            return content

        assert self.port is not None
        cache_key = (self.host, self.port)
        cached = self.SOCKET_CACHE.get(cache_key)
        s = None
        if cached is not None:
            s, expiry = cached
            if expiry == 0 or (expiry is not None and time.time() > expiry):
                s = None
                del self.SOCKET_CACHE[cache_key]
        if s is None:
            s = socket.socket(
                family=socket.AF_INET, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
            )

            s.connect((self.host, self.port))

            if self.scheme == "https":
                ctx = ssl.create_default_context()
                s = ctx.wrap_socket(s, server_hostname=self.host)

        request = "GET {} HTTP/1.1\r\n".format(self.path)
        request += "Host: {}\r\n".format(self.host)
        request += "User-Agent: WebBrowserEngineering\r\n"
        request += "Accept-Encoding: gzip\r\n"
        request += "\r\n"
        s.send(request.encode("utf8"))

        response = s.makefile("rb")  # raw bytes for gzip compatibility
        statusline = response.readline().decode("utf8")
        version, status, explanation = statusline.split(" ", 2)
        # e.g. "HTTP/1.0", "200", "OK"

        response_headers = {}
        while True:
            line = response.readline().decode("utf8")
            if line == "\r\n":
                break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()

        if status.startswith("3"):
            if max_redirects == 0:
                raise Exception("too many redirects")
            location = response_headers["location"]
            if location.startswith("/"):
                location = "{}://{}{}".format(self.scheme, self.host, location)
            return URL(location).request(max_redirects=max_redirects - 1)

        expiry: float | None = None
        cache_control = response_headers.get("cache-control", "")
        if "no-store" in cache_control:
            expiry = 0  # 0 means don't cache
        elif "max-age=" in cache_control:
            max_age = int(cache_control.split("max-age=")[1].split(",")[0])
            expiry = time.time() + max_age
        else:
            expiry = 0  # unknown value, don't cache

        transfer_encoding = response_headers.get("transfer-encoding")
        if transfer_encoding == "chunked":
            body = self.read_chunked(response)
        elif "content-length" in response_headers:
            content_length = int(response_headers["content-length"])
            body = response.read(content_length)
        else:
            # No framing info: the body runs until the server closes the
            # socket, so this connection can't be reused.
            body = response.read()
            expiry = 0
        if transfer_encoding not in (None, "chunked"):
            raise Exception("unsupported transfer-encoding: " + transfer_encoding)

        # Undo Content-Encoding (we only advertised gzip).
        content_encoding = response_headers.get("content-encoding")
        if content_encoding == "gzip":
            body = gzip.decompress(body)
        elif content_encoding is not None:
            raise Exception("unsupported content-encoding: " + content_encoding)

        self.SOCKET_CACHE[cache_key] = (s, expiry)

        return body.decode("utf8", errors="replace")

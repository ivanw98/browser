import socket
import ssl


class URL:
    ALLOW_LIST = ["http", "https", "file", "data", "view-source"]
    SOCKET_CACHE: dict[tuple[str, int], socket.socket] = {}

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

    def request(self) -> str:
        if self.scheme == "file":
            with open(self.path, "r", encoding="utf-8") as f:
                return f.read()

        if self.scheme == "data":
            _, content = self.path.split(",", 1)
            return content

        assert self.port is not None
        cache_key = (self.host, self.port)
        s = self.SOCKET_CACHE.get(cache_key)
        if s is None:
            s = socket.socket(
                family=socket.AF_INET, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
            )

            s.connect((self.host, self.port))

            if self.scheme == "https":
                ctx = ssl.create_default_context()
                s = ctx.wrap_socket(s, server_hostname=self.host)

        request = "GET {} HTTP/1.0\r\n".format(self.path)
        request += "Host: {}\r\n".format(self.host)
        request += "User-Agent: WebBrowserEngineering\r\n"
        request += "\r\n"
        s.send(request.encode("utf8"))

        response = s.makefile("r", encoding="utf8", newline="\r\n")

        statusline = response.readline()
        version, status, explanation = statusline.split(" ", 2)
        # e.g. "HTTP/1.0", "200", "OK"

        response_headers = {}
        while True:
            line = response.readline()
            if line == "\r\n":
                break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()

        assert "transfer-encoding" not in response_headers
        assert "content-encoding" not in response_headers

        content_length = int(response_headers["content-length"])

        content = response.read(content_length)

        return content

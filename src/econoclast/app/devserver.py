"""Developer preview: the app's UI in a browser, backed by the same Api over a tiny RPC.

    econoclast app --browser

Only for working on the UI (and for automated UI checks); people use the native window.
Binds to 127.0.0.1 only.
"""

from __future__ import annotations

import json
import mimetypes
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from econoclast.app.api import WEB, Api


def serve(port: int = 7777, *, open_browser: bool = True) -> None:
    api = Api()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a) -> None:  # noqa: ANN002
            pass

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            rel = "index.html" if path in ("/", "") else path.lstrip("/")
            target = (WEB / rel).resolve()
            if not str(target).startswith(str(WEB.resolve())) or not target.is_file():
                self.send_error(404)
                return
            body = target.read_bytes()
            self.send_response(200)
            ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            if target.suffix == ".js":
                ctype = "text/javascript"
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802
            if not self.path.startswith("/rpc/"):
                self.send_error(404)
                return
            name = self.path[len("/rpc/"):]
            fn = getattr(api, name, None)
            if name.startswith("_") or not callable(fn):
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length") or 0)
            args = json.loads(self.rfile.read(length) or b"[]") if length else []
            try:
                result = {"ok": True, "result": fn(*args)}
            except Exception as exc:  # noqa: BLE001
                result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            body = json.dumps(result, default=str).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/?bridge=http"
    print(f"Econoclast UI preview: {url}")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


__all__ = ["serve"]

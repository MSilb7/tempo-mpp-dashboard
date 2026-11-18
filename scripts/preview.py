"""Loopback-only preview: serve synthetic UI assets, never repository/private data."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
ASSETS = {'/', '/index.html', '/app.js', '/style.css', '/data/demo.json'}


class PreviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_head(self):
        if unquote(urlsplit(self.path).path) not in ASSETS:
            self.send_error(404)
            return None
        return super().send_head()


if __name__ == '__main__':
    print('Synthetic preview: http://127.0.0.1:8000', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8000), PreviewHandler).serve_forever()

"""Serves Frontend/ on http://localhost:3001 with caching disabled, so the browser always loads the current
index.html / app.js / style.css (python -m http.server lets browsers keep stale copies)."""
import functools
import http.server
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Frontend')
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 3001


class NoCache(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, must-revalidate')
        self.send_header('Expires', '0')
        super().end_headers()

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    handler = functools.partial(NoCache, directory=ROOT)
    with http.server.ThreadingHTTPServer(('', PORT), handler) as srv:
        print(f'SonicVitals dashboard on http://localhost:{PORT} (no caching)', flush=True)
        srv.serve_forever()

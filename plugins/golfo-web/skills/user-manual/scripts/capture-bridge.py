#!/usr/bin/env python3
"""Local bridge between the browser and the disk for user-manual captures and publishing.

Serves a directory (capture-snippet.js, frame-driver.js, the manual to publish) with CORS for ONE
allowed origin and accepts POSTed JSON exports, so captures never depend on browser downloads.

    python3 capture-bridge.py --origin https://app.local.test:8443 --directory <skill>/scripts \
        --exports /tmp/um-exports --port 8767

Security: binds to 127.0.0.1 only, answers CORS only for --origin, rejects POSTs from any other
origin and accepts only plain `[a-z0-9-]+.json` names inside --exports. Stop it when done.
"""
import argparse
import functools
import http.server
import json
import re
from pathlib import Path

EXPORT_NAME_PATTERN = re.compile(r'^[a-z0-9-]+\.json$')


class CaptureBridgeHandler(http.server.SimpleHTTPRequestHandler):
    """Serves static files and stores JSON exports for a single allowed origin."""

    allowed_origin = ''
    exports_directory = Path('.')

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', self.allowed_origin)
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST')
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_POST(self):
        name = self.path.strip('/')
        if self.headers.get('Origin') != self.allowed_origin or not EXPORT_NAME_PATTERN.match(name):
            self.send_response(403)
            self.end_headers()
            return
        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        try:
            json.loads(body)
        except ValueError:
            self.send_response(400)
            self.end_headers()
            return
        self.exports_directory.mkdir(parents=True, exist_ok=True)
        (self.exports_directory / name).write_bytes(body)
        self.send_response(204)
        self.end_headers()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--origin', required=True, help='Only origin allowed to read files and POST exports.')
    parser.add_argument('--directory', default=str(Path(__file__).parent), help='Directory served over GET.')
    parser.add_argument('--exports', default='/tmp/um-exports', help='Directory where POSTed exports are written.')
    parser.add_argument('--port', type=int, default=8767)
    arguments = parser.parse_args()
    CaptureBridgeHandler.allowed_origin = arguments.origin
    CaptureBridgeHandler.exports_directory = Path(arguments.exports)
    handler = functools.partial(CaptureBridgeHandler, directory=arguments.directory)
    print(f'capture-bridge: http://127.0.0.1:{arguments.port} for {arguments.origin} -> {arguments.exports}')
    http.server.ThreadingHTTPServer(('127.0.0.1', arguments.port), handler).serve_forever()


if __name__ == '__main__':
    main()

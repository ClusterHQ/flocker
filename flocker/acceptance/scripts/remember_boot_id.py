"""
HTTP server that reports both current and previously recorded boot_id,
the latter stored persistently on disk.
"""

from sys import argv
from json import dumps
import os

from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer


# Try to write out file ASAP, to increase chances of hitting race
# condition with dataset setup:
with file("/proc/sys/kernel/random/boot_id") as boot_f:
    boot_id = boot_f.read()

file_path = os.path.join(argv[1], "written.json")
if not os.path.exists(file_path):
    with file(file_path, "w") as f:
        f.write(boot_id)
written = file(file_path).read()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(dumps({"current": boot_id,
                                "written": written}))
        self.wfile.close()


httpd = HTTPServer((b"0.0.0.0", 8080), Handler)
httpd.serve_forever()

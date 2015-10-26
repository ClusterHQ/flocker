"""
HTTP server that exits after responding to a GET request.
"""

from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
import os
import time


class Handler(BaseHTTPRequestHandler):
    def do_GET(s):
        s.send_response(200)
        s.send_header("content-length", "2")
        s.end_headers()
        s.wfile.write(b"hi")
        s.wfile.flush()
        s.wfile.close()
        # Try to ensure enough time for bytes to make it out before exiting:
        time.sleep(0.1)
        os._exit(1)

httpd = HTTPServer((b"0.0.0.0", 8080), Handler)
httpd.serve_forever()

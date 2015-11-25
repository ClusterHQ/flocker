"""
HTTP server that exits after responding to a GET request.
"""

from os import urandom

from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer

PROCESS_UNIQUE_VALUE = urandom(32).encode("hex")


class Handler(BaseHTTPRequestHandler):
    def do_GET(s):
        s.send_response(200)
        s.send_header(
            b"content-length",
            u"{}".format(len(PROCESS_UNIQUE_VALUE)).encode("ascii")
        )
        s.end_headers()
        s.wfile.write(PROCESS_UNIQUE_VALUE)
        s.wfile.flush()
        s.wfile.close()

httpd = HTTPServer((b"0.0.0.0", 8080), Handler)
httpd.handle_request()

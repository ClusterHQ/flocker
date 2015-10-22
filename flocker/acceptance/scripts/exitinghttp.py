"""
HTTP server that exits after responding to a GET request.
"""

from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
import os


class Handler(BaseHTTPRequestHandler):
    def do_GET(s):
        s.send_response(200)
        s.end_headers()
        s.wfile.write(b"hi")
        s.wfile.close()
        os._exit(1)

httpd = HTTPServer((b"0.0.0.0", 8080), Handler)
httpd.serve_forever()

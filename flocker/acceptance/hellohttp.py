"""
HTTP server that returns a fixed string.
"""

from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(s):
        s.wfile.write(b"hi")
        s.wfile.close()


httpd = HTTPServer((b"0.0.0.0", 8080), Handler)
httpd.serve_forever()

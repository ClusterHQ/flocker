"""
HTTP server that returns its environment variables as JSON.
"""

from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from json import dumps
from os import environ


class Handler(BaseHTTPRequestHandler):
    """
    Return the current environment in HTTP response.
    """
    def do_GET(s):
        s.send_response(200)
        s.send_header("content-type", "text/json")
        s.end_headers()
        s.wfile.write(dumps(environ.items()))
        s.wfile.close()


httpd = HTTPServer((b"0.0.0.0", 8080), Handler)
httpd.serve_forever()

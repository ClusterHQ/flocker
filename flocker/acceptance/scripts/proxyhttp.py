"""
HTTP server that proxies requests to a remote server based on Docker
linking environment variables.
"""

from urllib import urlopen
from os import getenv
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer

DEST_URL = "http://%s:%s/" % (
    getenv("DEST_PORT_80_TCP_ADDR"), getenv("DEST_PORT_80_TCP_PORT"))


class Handler(BaseHTTPRequestHandler):
    def do_GET(s):
        s.send_response(200)
        s.end_headers()
        s.wfile.write(urlopen(DEST_URL).read())
        s.wfile.close()


httpd = HTTPServer((b"0.0.0.0", 8081), Handler)
httpd.serve_forever()

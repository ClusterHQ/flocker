"""
HTTP server that ensures it can write to given directory as a non-root
user, then returns "hi".
"""

from sys import argv
from os import setuid
from pwd import getpwnam
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(s):
        s.send_response(200)
        s.end_headers()
        # Ensure we can write to given directory:
        try:
            with open(argv[1] + "/test", "w") as f:
                f.write(b"testing 123")
        except Exception as e:
            s.wfile.write(str(e.__class__) + ": " + str(e))
        else:
            s.wfile.write(b"hi")
        s.wfile.close()

setuid(getpwnam("nobody")[2])
httpd = HTTPServer((b"0.0.0.0", 8080), Handler)
httpd.serve_forever()

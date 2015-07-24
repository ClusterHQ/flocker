"""
HTTP server that ensures it can write to given directory as a non-root
user, then returns "hi".
"""

from sys import argv
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(s):
        # Ensure we can write to given directory:
        try:
            with open(argv[1], "w") as f:
                f.write(b"testing 123")
        except Exception as e:
            s.wfile.write(str(e.__class__) + ": " + str(e))
        else:
            s.wfile.write(b"hi")
        s.wfile.close()


httpd = HTTPServer((b"0.0.0.0", 8080), Handler)
httpd.serve_forever()

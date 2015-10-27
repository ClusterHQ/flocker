"""
HTTP server that exits after responding to a GET request.
"""

from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(s):
        s.send_response(200)
        s.send_header("content-length", "2")
        s.end_headers()
        s.wfile.write(b"hi")
        s.wfile.flush()
        s.wfile.close()
        raise SystemExit()

httpd = HTTPServer((b"0.0.0.0", 8080), Handler)
httpd.serve_forever()

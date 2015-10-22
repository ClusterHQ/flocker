"""
HTTP server that writes data to a specified file on POST, or reads and
returns data from a specified file on GET.
"""

from sys import argv

try:
    from urlparse import parse_qs
except ImportError:
    from cgi import parse_qs

from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(s):
        length = int(s.headers['content-length'])
        postvars = parse_qs(
            s.rfile.read(length),
            keep_blank_values=1
        )
        try:
            with open(argv[1] + '/test', "w") as f:
                f.write(postvars["data"][0])
        except Exception as e:
            s.wfile.write(str(e.__class__) + ": " + str(e))
        s.send_response(200)
        s.end_headers()
        s.wfile.write(b"ok")
        s.wfile.close()

    def do_GET(s):
        s.send_response(200)
        s.end_headers()
        if len(argv) > 1:
            try:
                with open(argv[1] + '/test', "r") as f:
                    data = f.read()
            except Exception as e:
                s.wfile.write(str(e.__class__) + ": " + str(e))
            else:
                s.wfile.write(data)
        else:
                s.wfile.write(b"ok")
        s.wfile.close()

httpd = HTTPServer((b"0.0.0.0", 8080), Handler)
httpd.serve_forever()

"""
HTTP server that returns the size of the mounted volume.
"""

from sys import argv
from subprocess import check_output

from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(s):
        s.send_response(200)
        s.end_headers()
        if len(argv) > 1:
            try:
                # format output is </dev/id>[/mount/point]
                # so we filter the mountpoint
                # returned device is '/dev/xvdb\\n'
                device_path = check_output([
                    'findmnt', '-n', '-m', '%s' % argv[1], '-o',
                    'SOURCE']).split('[')[0].split('\n')[0]

                command = ["/bin/lsblk", "--noheadings", "--bytes",
                           "--output", "SIZE", device_path]
                # lskblk is filtered to just return the size of the
                # underlying device in filtered columns, we grab the
                # specific one which contains the size in bytes.
                command_output = check_output(command).split('\n')[0]
                device_size = str(int(command_output.strip()))
            # generally this will only fail if lsblk fails,
            # becuase we run in a stable container environment
            # so catching 'Exception' here is preceived as OK.
            except Exception as e:
                s.wfile.write(str(e.__class__) + ": " + str(e))
            else:
                s.wfile.write(device_size)
        else:
            s.wfile.write(b"ok")
        s.wfile.close()

httpd = HTTPServer((b"0.0.0.0", 8080), Handler)
httpd.serve_forever()

"""
HTTP server that returns the size of the mounted volume.
"""

from subprocess import check_output

from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(s):
        s.end_headers()
        try:
            # format output is </dev/id>[/mount/point]
            # so we filter the mountpoint
            device_path = check_output(['findmnt', '-n',
                                        '-m', '/sizedvoldata',
                                        '-o', 'SOURCE']).split('[')[0]

            command = ["/bin/lsblk", "--noheadings", "--bytes",
                       "--output", "SIZE", device_path]
            # lskblk is filtered to just return the size of the
            # underlying device in filtered columns, we grab the
            # specific one which contains the size in bytes.
            command_output = check_output(command).split('\n')[0]
            device_size = str(int(command_output.strip()))
        except Exception as e:
            s.send_response(500)
            s.wfile.write(str(e.__class__) + ": " + str(e))
        else:
            s.send_response(200)
            s.wfile.write(device_size)
        s.wfile.close()

httpd = HTTPServer((b"0.0.0.0", 8080), Handler)
httpd.serve_forever()

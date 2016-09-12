"""
HTTP server that returns the size of the mounted volume.
"""

from sys import argv
from subprocess import check_output, STDOUT, CalledProcessError

from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer


class CalledProcessErrorWithOutput(CalledProcessError):
    """
    Like ``CalledProcessError`` but includes the suppied ``output`` when
    coerced to ``str``.
    """
    def __str__(self):
        return (
            "Command '%s' "
            "returned non-zero exit status %d "
            "and output %r" % (
                self.cmd, self.returncode, self.output,
            )
        )


def check_output_and_error(*args, **kwargs):
    """
    Like ``check_output`` but captures the ``stderr`` and raises an exception
    that incudes all the ``stdout`` and ``stderr`` output when coerced to
    ``str``.
    """
    kwargs["stderr"] = STDOUT
    try:
        return check_output(*args, **kwargs)
    except CalledProcessError as e:
        raise CalledProcessErrorWithOutput(
            returncode=e.returncode,
            cmd=e.cmd,
            output=e.output,
        )


class Handler(BaseHTTPRequestHandler):
    def do_GET(s):
        s.send_response(200)
        s.end_headers()
        if len(argv) > 1:
            try:
                # format output is </dev/id>[/mount/point]
                # so we filter the mountpoint
                # returned device is '/dev/xvdb\\n'
                output = check_output_and_error(
                    ['findmnt', '-n', '-m', '%s' % argv[1], '-o', 'SOURCE'],
                )
                device_path = output.split('[')[0].split('\n')[0]

                # lskblk is filtered to just return the size of the
                # underlying device in filtered columns, we grab the
                # specific one which contains the size in bytes.
                output = check_output_and_error(
                    ["/bin/lsblk", "--noheadings", "--bytes",
                     "--output", "SIZE",
                     device_path]
                )
                device_size = str(int(output.split('\n')[0].strip()))
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

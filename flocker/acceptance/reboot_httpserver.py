"""
HTTP server used by reboot acceptance tests.

First command-line argument is directory which is expected to be Docker
volume that will persist across reboots.
"""

import BaseHTTPServer
import sys
import os
from subprocess import check_output


FIRST_BOOT_PATH = os.path.join(sys.argv[1], "first_boot")


def boot_time():
    """
    :return: ``bytes`` with time this machine was booted.
    """
    return check_output([b"uptime", b"--since"])


def hostname():
    """
    :return: ``bytes`` with the hostname of the container this process is
    running in. Corresponds to the Docker container ID.
    """
    return check_output([b"hostname"])


class RebootHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    """
    Respond to HTTP requests with bootup time of first time process was
    run, as well as current run's bootup time.
    """

    def do_GET(s):
        s.send_response(200)
        s.send_header("Content-type", "text/plain")
        s.end_headers()
        s.wfile.write(file(FIRST_BOOT_PATH).read() + b"\n")
        s.wfile.write(boot_time() + "\n")
        s.wfile.write(hostname())


if __name__ == '__main__':
    if not os.path.exists(FIRST_BOOT_PATH):
        with file(FIRST_BOOT_PATH, "w") as f:
            f.write(boot_time())

    httpd = BaseHTTPServer.HTTPServer((b"0.0.0.0", 12345), RebootHandler)
    httpd.serve_forever()

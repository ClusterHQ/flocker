# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
A script which is called by ``run_process`` in the ``test_process` module.
The returncode, stdout and stderr can all be supplied as command line arguments
so that we can test how ``run_process`` captures process output and how it
behaves when sub-processes exit with different return codes.
If the supplied returncode is < 0 the script will send that integer as a signal
to its own PID.
"""

import os
import sys
import time

from twisted.python.usage import Options


class ScriptOptions(Options):
    optParameters = [
        ["returncode", None, None, "Exit with this status", int],
        ["stdout", None, None, "Print this to stdout"],
        ["stderr", None, None, "Print this to stderr"],
    ]


def main():
    options = ScriptOptions()
    options.parseOptions(sys.argv[1:])
    sys.stdout.write(options["stdout"])
    sys.stdout.flush()
    sys.stderr.write(options["stderr"])
    sys.stderr.flush()
    returncode = options["returncode"]
    if returncode < 0:
        os.kill(os.getpid(), abs(returncode))
        time.sleep(10)
    return returncode

if __name__ == "__main__":
    raise SystemExit(main())

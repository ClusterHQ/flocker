# Copyright ClusterHQ Inc.  See LICENSE file for details.
import os
import sys

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
    else:
        return returncode

if __name__ == "__main__":
    raise SystemExit(main())

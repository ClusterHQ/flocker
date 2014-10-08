# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Tools for running commands.
"""
import sys
from pipes import quote
from subprocess import check_call, CalledProcessError


def run(command, **kwargs):
    """
    Echo and run a command..

    :param list command: Command to run.
    :param kwargs: Extra args to pass to ``subprocess.call``.
    """
    sys.stdout.write("Running %s\n" % (b' '.join(map(quote, command))))
    try:
        check_call(command, **kwargs)
    except CalledProcessError as e:
        sys.stderr.write('Failed %d: %s\n'
                         % (e.returncode, ' '.join(map(quote, command))))
        raise SystemExit(e.returncode)

# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Testing tools related to iptables.
"""

from subprocess import PIPE, Popen, check_output

class _Preserver(object):
    def preserve(self):
        self.rules = check_output([b"iptables-save"])


    def restore(self):
        process = Popen([b"iptables-restore"], stdin=PIPE)
        process.stdin.write(self.rules)
        process.stdin.close()
        exit_code = process.wait()
        if exit_code != 0:
            raise Exception(
                "Possibly failed to restore iptables configuration: %s" % (
                    exit_code,))



def preserve_iptables():
    """
    :py:func:`preserve_iptables` is a fixture which saves the current iptables
    configuration and restores it later.
    """
    preserver = _Preserver()
    preserver.preserve()
    return preserver
    return restore

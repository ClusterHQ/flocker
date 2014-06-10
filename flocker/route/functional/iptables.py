# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Testing tools related to iptables.
"""

from subprocess import PIPE, Popen, check_output

class _Preserver(object):
    """
    Implementation helper for :py:func:`preserve_iptables`.
    """
    def preserve(self):
        """
        Use ``iptables-save`` to record the current rules.
        """
        self.rules = check_output([b"iptables-save"])


    def restore(self):
        """
        Use ``iptables-restore`` to put the previously recorded rules back on
        the system.

        :raise Exception: If the ``iptables-restore`` command exits with an
            error code.
        """
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
    configuration and restores it later.  Use the :py:meth:`restore`: method of
    the returned object to restore the rules as they were at the time this
    function was called.
    """
    preserver = _Preserver()
    preserver.preserve()
    return preserver

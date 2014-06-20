# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Testing tools related to iptables.
"""

from subprocess import PIPE, Popen, check_output


def get_iptables_rules():
    """
    Return a list of :command:`iptables-save`-formatted rule strings with
    comments and packet/byte counter lines removed.

    This also removes the information about the default policy for chains
    (which might someday be important).
    """
    # Naive use of iptables-save | iptables-restore isn't actually a safe
    # way to restore original configuration.
    # https://bugzilla.netfilter.org/show_bug.cgi?id=960
    tables = [b"filter", b"nat", b"mangle", b"raw", b"security"]

    # Add material to flush every table first.  This overcomes the lack of
    # information about "empty" tables in the bare iptables-save output.
    flush_rules = "".join(
        "*{table}\nCOMMIT\n".format(table=table) for table in tables)
    rules = flush_rules + check_output([b"iptables-save"])
    return [
            rule
            for rule in rules.splitlines()
            # Comments don't matter.  They always differ because they
            # include timestamps.
            if not rule.startswith("#")
            # Chain data could matter but doesn't.  The implementation
            # doesn't mess with this stuff.  It typically differs in
            # uninteresting ways - such as matched packet counters.
            and not rule.startswith(":")]


class _Preserver(object):
    """
    Implementation helper for :py:func:`preserve_iptables`.
    """
    def preserve(self):
        """
        Use ``iptables-save`` to record the current rules.
        """
        self._saved_rules = get_iptables_rules()


    def restore(self):
        """
        Use ``iptables-restore`` to put the previously recorded rules back on
        the system.

        :raise Exception: If the ``iptables-restore`` command exits with an
            error code.
        """
        process = Popen([b"iptables-restore"], stdin=PIPE)
        process.stdin.write(b'\n'.join(self._saved_rules) + b'\n')
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

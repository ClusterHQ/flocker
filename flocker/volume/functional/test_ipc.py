# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Functional tests for IPC."""

import subprocess
from twisted.python.filepath import FilePath

from .._ipc import ProcessNode
from ..test.test_ipc import make_inode_tests


def make_cat_processnode(test_case):
    """Create a ``ProcessNode`` that just runs ``cat``.

    :return: ``ProcessNode`` that runs ``cat``.
    """
    return ProcessNode(initial_command_arguments=[b"cat"])


class ProcessINodeTests(make_inode_tests(make_cat_processnode)):
    """``INode`` tests for ``ProcessNode``."""


def make_real_sshnode(test_case):
    """Create a ``ProcessNode`` that can SSH into the local machine.

    :param TestCase test_case: The test case to use.

    :return: A ``ProcessNode`` instance.
    """
    sshd_path = FilePath(test_case.mktemp())
    sshd_path.makedirs()
    subprocess.check_call(
        [b"ssh-keygen", b"-f", sshd_path.child(b"sshd_host_key").path,
         b"-N", b""])
    # XXX use twisted.conch.tap code...

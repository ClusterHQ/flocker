# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Unit tests for IPC.
"""

from __future__ import absolute_import

from zope.interface.verify import verifyObject

from .. import INode, FakeNode
from ...testtools import TestCase, assertNoFDsLeaked


def make_inode_tests(fixture):
    """
    Create a TestCase for ``INode``.

    :param fixture: A fixture that returns a :class:`INode` provider which
        will work with any arbitrary valid program with arguments.
    """
    class INodeTests(TestCase):
        """Tests for :class:`INode` implementors.

        May be functional tests depending on the fixture.
        """
        def test_interface(self):
            """
            The tested object provides :class:`INode`.
            """
            node = fixture(self)
            self.assertTrue(verifyObject(INode, node))

        def test_run_no_fd_leakage(self):
            """
            No file descriptors are leaked by ``run()``.
            """
            node = fixture(self)
            with assertNoFDsLeaked(self):
                with node.run([b"cat"]):
                    pass

        def test_run_exceptions_pass_through(self):
            """
            Exceptions raised in the context manager are not swallowed.
            """
            node = fixture(self)

            def run_node():
                with node.run([b"cat"]):
                    raise RuntimeError()
            self.assertRaises(RuntimeError, run_node)

        def test_run_no_fd_leakage_exceptions(self):
            """
            No file descriptors are leaked by ``run()`` if exception is
            raised within the context manager.
            """
            node = fixture(self)
            with assertNoFDsLeaked(self):
                try:
                    with node.run([b"cat"]):
                        raise RuntimeError()
                except RuntimeError:
                    pass

        def test_run_writeable(self):
            """
            The returned object from ``run()`` is writeable.
            """
            node = fixture(self)
            with node.run([b"python", b"-c",
                           b"import sys; sys.stdin.read()"]) as writer:
                writer.write(b"hello")
                writer.write(b"there")

        def test_get_output_no_leakage(self):
            """
            No file descriptors are leaked by ``get_output()``.
            """
            node = fixture(self)
            with assertNoFDsLeaked(self):
                node.get_output([b"echo", b"hello"])

        def test_get_output_result_bytes(self):
            """
            ``get_output()`` returns a result that is ``bytes``.
            """
            node = fixture(self)
            result = node.get_output([b"echo", b"hello"])
            self.assertIsInstance(result, bytes)

    return INodeTests


class FakeINodeTests(make_inode_tests(lambda t: FakeNode([b"hello"]))):
    """``INode`` tests for ``FakeNode``."""

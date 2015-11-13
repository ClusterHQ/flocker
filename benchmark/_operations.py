# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Operations for the control service benchmarks.
"""

from zope.interface import Interface


class IProbe(Interface):
    """A probe that performs an operation."""

    def run():
        """
        Run the operation.  This should run with as little overhead as
        possible, in order to ensure benchmark measurements are accurate.

        :return: A Deferred firing with the result of the operation.
        """

    def cleanup():
        """
        Perform any cleanup required after the operation.  This is performed
        outside the benchmark measurement.

        :return: A Deferred firing when the cleanup is finished.
        """


class IOperation(Interface):
    """An operation that can be performed."""

    def get_probe():
        """
        Get a probe for the operation. To ensure sequential operations
        perform real work, the operation may return a different
        probe each time.
        """

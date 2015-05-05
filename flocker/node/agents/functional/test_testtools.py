# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node.agents.testtools``.
"""

from ..testtools import (
    make_icindervolumemanager_tests, tidy_cinder_client_for_test
)


class TidyCinderVolumeManagerInterfaceTests(
        make_icindervolumemanager_tests(
            client_factory=lambda test_case: (
                tidy_cinder_client_for_test(test_case).volumes
            )
        )
):
    """
    """

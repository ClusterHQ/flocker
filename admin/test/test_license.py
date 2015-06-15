# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Tests for LICENSE file.
"""

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath

from datetime import datetime

# TODO put this in a common test tools
FLOCKER_PATH = FilePath(__file__).parent().parent().parent()


class LicenseTests(SynchronousTestCase):
    """
    Tests for LICENSE.
    """

    def test_current_year(self):
        """
        The current year is in a LICENSE file at the root of the Flocker
        directory.
        """
        self.assertIn(
            'Copyright 2014-{year} ClusterHQ'.format(year=datetime.now().year),
            FLOCKER_PATH.child('LICENSE').getContent()
        )

# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for deploying applications.
"""

class DeploymentTests(TestCase):
    """
    Tests for deploying applications.

    Similar to http://doc-dev.clusterhq.com/gettingstarted/tutorial/moving-applications.html#starting-an-application
    """
    def test_deploy(self):
        """
        Call a 'deploy' utility function with an application and deployment
        config and watch docker ps output.
        """

import mock

from twisted.python.usage import UsageError

from flocker.testtools import TestCase

from ..acceptance import CommonOptions
from ..cluster_setup import RunOptions


class RunOptionsTest(TestCase):

    @mock.patch.object(CommonOptions, 'postOptions')
    def test_purpose(self, mock_postOpts):
        """
        RunOptions are parsed correctly when a purpose is provided
        """
        arg_options = (
            "--distribution", "ubuntu-14.04",
            "--provider", "aws",
            "--purpose", "test"
        )
        run_options = RunOptions(self.mktemp())
        run_options.parseOptions(arg_options)
        self.assertEquals(run_options['purpose'], 'test')

from twisted.python.usage import UsageError

from flocker.testtools import TestCase

from ..acceptance import CommonOptions
from ..cluster_setup import RunOptions


class RunOptionsForTest(RunOptions):

    def postOptions(self):
        pass

class RunOptionsTest(TestCase):

    def test_purpose(self):
        """
        RunOptions are parsed correctly when a purpose is provided
        """
        arg_options = (
            "--distribution", "ubuntu-14.04",
            "--provider", "aws",
            "--purpose", "test"
        )
        run_options = RunOptionsForTest(self.mktemp())
        run_options.parseOptions(arg_options)
        self.assertEquals(run_options['purpose'], 'test')

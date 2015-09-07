from textwrap import dedent

from twisted.python.filepath import FilePath
from twisted.trial.unittest import SynchronousTestCase

from flocker import __version__ as version
from flocker.common.version import get_installable_version
from flocker.testtools import run_process


class VersionExtensionsTest(SynchronousTestCase):

    def test_version_prompt(self):
        temp_dir = FilePath(self.mktemp())
        temp_dir.makedirs()
        source_file = temp_dir.child('contents.rst')
        source_file.setContent(dedent('''
            .. version-prompt:: bash $

               $ PRE-|latest-installable|-POST
            '''))
        target = temp_dir.child('contents.html')
        run_process([
            'sphinx-build', '-b', 'html',
            '-C',   # don't look for config file, use -D flags instead
            '-D', 'extensions=flocker.docs.version_extensions',
            temp_dir.path,      # directory containing source/config files
            temp_dir.path,      # directory containing build files
            source_file.path])  # source file to process
        content = target.getContent()
        expected = 'PRE-{}-POST'.format(get_installable_version(version))
        self.assertIn(expected, content)

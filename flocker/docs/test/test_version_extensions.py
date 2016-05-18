from textwrap import dedent

from flocker import __version__ as version
from flocker.common.version import get_installable_version
from flocker.testtools import TestCase, run_process


class VersionExtensionsTest(TestCase):
    """
    Tests for Sphinx version extensions.
    """

    def test_version_prompt(self):
        """
        The ``version-prompt`` directive replaces the placemarker
        ``|latest-installable|`` in a source file with the current
        installable version in the output file.
        """
        source_directory = self.make_temporary_directory()
        source_file = source_directory.child('contents.rst')
        source_file.setContent(dedent('''
            .. version-prompt:: bash $

               $ PRE-|latest-installable|-POST
            '''))
        destination_directory = self.make_temporary_directory()
        run_process([
            'sphinx-build', '-b', 'html',
            '-C',   # don't look for config file, use -D flags instead
            '-D', 'extensions=flocker.docs.version_extensions',
            # directory containing source/config files
            source_directory.path,
            # directory containing build files
            destination_directory.path,
            source_file.path])  # source file to process
        expected = 'PRE-{}-POST'.format(get_installable_version(version))
        content = destination_directory.child('contents.html').getContent()
        self.assertIn(expected, content)

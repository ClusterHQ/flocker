# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``admin.release``.
"""

from git import Repo
from testtools.matchers import Contains, Equals
from twisted.python.filepath import FilePath
from flocker.testtools import TestCase, run_process


def repository_path():
    """
    :return: The nearest ``FilePath`` in parents of this module that have a
        ``flocker/__init__.py`` file that matches what will be imported as
        ``flocker``.
    """
    current_module_path = FilePath(__file__)
    for parent in current_module_path.parents():
        flocker_init = parent.descendant(['flocker', '__init__.py'])
        if flocker_init.exists():
            nearest_flocker_path = flocker_init.parent()
            nearest_flocker_repository = parent
            break
    else:
        raise ImportError(
            "Could not find ``flocker.__init__.py`` "
            "in any parent directories: "
            "{!r}".format(current_module_path.parents())
        )

    import flocker
    imported_flocker_path = FilePath(flocker.__file__).parent()

    if imported_flocker_path != nearest_flocker_path:
        raise ImportError(
            "Imported flocker modules are not from this repository. "
            "Imported: {!r},"
            "Repository: {!r}".format(
                imported_flocker_path, nearest_flocker_path
            )
        )

    return nearest_flocker_repository

REPOSITORY_PATH = repository_path()
INITIALIZE_RELEASE_PATH = REPOSITORY_PATH.descendant(
    ['admin', 'initialize-release']
)


class InitializeReleaseScriptTests(TestCase):
    """
    Functional tests for the ``admin/initialize-release`` script.
    """
    def test_help(self):
        """
        The script is executable and has some meaningful ``--help``.
        """
        result = run_process(
            [INITIALIZE_RELEASE_PATH.path, '--help']
        )
        self.expectThat(result.status, Equals(0))
        self.expectThat(result.output, Contains('Usage: initialize-release'))

    def test_run(self):
        """
        The script creates a new release version branch in a new working
        directory and prints some shell commands to ``stdout``.
        """
        expected_version = "9.9.9"
        script_path = self.make_temporary_directory()
        repo_path = script_path.sibling(
            'flocker-release-{}'.format(expected_version)
        )
        result = run_process(
            [INITIALIZE_RELEASE_PATH.path,
             '--flocker-version={}'.format(expected_version)],
            cwd=script_path.path
        )
        self.expectThat(result.status, Equals(0))
        self.expectThat(
            result.output,
            Contains('export VERSION={}'.format(expected_version))
        )
        self.expectThat(
            Repo(path=repo_path.path).active_branch.name,
            Equals('release/flocker-{}'.format(expected_version))
        )

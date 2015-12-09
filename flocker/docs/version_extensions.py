# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Sphinx extension to add directives to allow files and code to include the
latest installable version of Flocker.
"""

import importlib
import os

from sphinx.directives.code import LiteralInclude
from sphinx.roles import XRefRole

from flocker import __version__ as version
from flocker.common.version import get_installable_version

from sphinx import addnodes
from sphinx.util import ws_re

PLACEHOLDER = u'|latest-installable|'


def remove_extension(template):
    """
    Given a filename or path of a template file, return the same without the
    template suffix.

    :param unicode template: The filename of or path to a template file which
        ends with '.template'.
    :return: The given filename or path without the '.template' suffix.
    """
    return template[:-len('.template')]


def make_changed_file(path, env):
    """
    Given the path to a template file, write a new file with:
        * The same filename, except without '.template' at the end.
        * A placeholder in the new file changed to the latest installable
          version of Flocker.

    This new file will be deleted on build completion.

    :param unicode path: The path to a template file.
    :param sphinx.environment.BuildEnvironment env: The Sphinx build
        environment
    """
    def remove_file(path):
        try:
            os.remove(path)
        except OSError:
            pass

    latest = get_installable_version(version)
    new_path = remove_extension(path)
    with open(path, 'r') as templated_file:
        with open(new_path, 'w') as new_file:
            new_file.write(templated_file.read().replace(PLACEHOLDER, latest))
            env.app.connect('build-finished',
                            lambda self, *args: remove_file(new_path))


class VersionDownload(XRefRole):
    """
    Similar to downloadable files, but:
        * Replaces a placeholder in the downloadable file with the latest
          installable version of Flocker.
        * Replaces the download link with one which strips '.template' from the
          end of the file name.
    """
    nodeclass = addnodes.download_reference

    def process_link(self, env, refnode, has_explicit_title, title, target):
        rel_filename, filename = env.relfn2path(target)
        make_changed_file(filename, env)

        return (remove_extension(title),
                ws_re.sub(' ', remove_extension(target)))


class VersionLiteralInclude(LiteralInclude):
    """
    Similar to LiteralInclude but replaces a placeholder with the latest
    installable version of Flocker. The filename of the file to be included
    must end with '.template'.
    """
    def run(self):
        document = self.state.document
        env = document.settings.env
        rel_filename, filename = env.relfn2path(self.arguments[0])
        make_changed_file(filename, env)
        self.arguments[0] = remove_extension(self.arguments[0])

        return LiteralInclude.run(self)


# Due to the dash in the name, the sphinx-prompt module is unloadable
# using a normal import - use the importlib machinery instead.
sphinx_prompt = importlib.import_module('sphinx-prompt')


class VersionPrompt(sphinx_prompt.PromptDirective):
    """
    Similar to PromptDirective but replaces a placeholder with the
    latest installable version of Flocker.

    Usage example:

    .. version-prompt:: bash $

       $ brew install flocker-|latest-installable|
    """
    def run(self):
        latest = get_installable_version(version)
        self.content = [item.replace(PLACEHOLDER, latest) for
                        item in self.content]
        return sphinx_prompt.PromptDirective.run(self)


def setup(app):
    app.add_directive('version-prompt', VersionPrompt)
    app.add_directive('version-literalinclude', VersionLiteralInclude)
    app.add_role('version-download', VersionDownload())

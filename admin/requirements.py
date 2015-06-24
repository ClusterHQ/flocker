# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Create requirements.txt and dev-requirements.txt from dependency.yml.
"""

from subprocess import check_output, check_call
from tempfile import mkdtemp
from twisted.python.filepath import FilePath
import yaml

from pyrsistent import PRecord, field


class VirtualEnv(PRecord):

    path = field(FilePath, mandatory=True)

    @classmethod
    def create(cls, path):
        check_call(["virtualenv", "--quiet", path.path])
        return cls(path=path)

    @property
    def pip(self):
        return self.path.descendant(["bin", "pip"])

    def install_packages(self, packages):
        check_call(
            [self.pip.path, 'install', '--quiet'] + packages,
            cwd=self.path.path,
        )

    def get_installed_packages(self):
        return check_output(
            [self.pip.path, 'freeze'],
            cwd=self.path.path
        ).splitlines()


def create_requirements(scratch_directory, top_level, deps):
    venv = VirtualEnv.create(scratch_directory)

    venv.install_packages(deps['package'])
    requirements = venv.get_installed_packages()
    venv.install_packages(deps['dev'])
    dev_requirements = [
        req for req in venv.get_installed_packages() if req not in requirements
    ]

    requirements_txt = top_level.child('requirements.txt')
    dev_requirements_txt = top_level.child('dev-requirements.txt')
    requirements_txt.setContent(
        "\n".join(requirements) + "\n"
    )
    requirements_txt.chmod(0o644)
    dev_requirements_txt.setContent(
        "\n".join(dev_requirements) + "\n"
    )
    dev_requirements_txt.chmod(0o644)


def main(args, top_level, base_path):
    deps = yaml.safe_load(top_level.child('dependencies.yml').getContent())

    scratch_directory = FilePath(mkdtemp())
    try:
        create_requirements(
            scratch_directory=scratch_directory,
            top_level=top_level, deps=deps,
        )
    finally:
        scratch_directory.remove()

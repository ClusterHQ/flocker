# This is a hack.
# https://clusterhq.atlassian.net/browse/FLOC-2528
from subprocess import check_output, check_call
from tempfile import mkdtemp
from twisted.python.filepath import FilePath
import yaml

from _preamble import TOPLEVEL

deps = yaml.safe_load(TOPLEVEL.child('dependencies.yml').getContent())

venv_dir = FilePath(mkdtemp())
check_call(["virtualenv", venv_dir.path])
pip = venv_dir.descendant(["bin", "pip"])
check_call([pip.path, 'install'] + deps['package'])

def get_installed_packages():
    reqs = check_output([pip.path, 'freeze']).splitlines()
    return [
        req for req in reqs
        # We don't want to include flocker in requirements.txt
        if not req.startswith('Flocker==')
        # https://github.com/pypa/pip/issues/2926
        and not req.startswith('-e ')
    ]

requirements = get_installed_packages()

TOPLEVEL.child('requirements.txt').setContent(
    "\n".join(requirements) + "\n"
)

check_call([pip.path, 'install'] + deps['dev'])

dev_requirements = [
    req for req in get_installed_packages() if req not in requirements
]

TOPLEVEL.child('dev-requirements.txt').setContent(
    "\n".join(dev_requirements) + "\n"
)

venv_dir.remove()

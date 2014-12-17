from twisted.trial.unittest import SynchronousTestCase

from .. import PackageSource
from .._install import (
    task_install_flocker,
    ZFS_REPO, CLUSTERHQ_REPO,
    Run, Put,
)


class FakeRunner(object):
    """
    Task runner that records the executed commands.
    """

    def __init__(self):
        self.commands = []

    def run(self, command):
        self.commands.append(Run(command=command))

    def put(self, content, path):
        self.commands.append(Put(content=content, path=path))


class TestInstallFlocker(SynchronousTestCase):
    """
    Tests for ``test_install_flocker``.
    """

    def test_no_arguments(self):
        commands = task_install_flocker()
        self.assertEqual(commands, [
            Run(command="yum install -y %s" % ZFS_REPO),
            Run(command="yum install -y %s" % CLUSTERHQ_REPO),
            Run(command="yum install -y clusterhq-flocker-node")
        ])

    def test_with_version(self):
        source = PackageSource(version="1.2.3")
        commands = task_install_flocker(package_source=source)
        self.assertEqual(commands, [
            Run(command="yum install -y %s" % ZFS_REPO),
            Run(command="yum install -y %s" % CLUSTERHQ_REPO),
            Run(command="yum install -y clusterhq-flocker-node-1.2.3-1")
        ])

    def test_with_branch(self):
        source = PackageSource(branch="branch")
        commands = task_install_flocker(
            package_source=source,
            distribution="fedora-20")
        self.assertEqual(commands, [
            Run(command="yum install -y %s" % ZFS_REPO),
            Run(command="yum install -y %s" % CLUSTERHQ_REPO),
            Put(content="""\
[clusterhq-build]
name=clusterhq-build
baseurl=http://build.clusterhq.com/results/omnibus/branch/fedora-20
gpgcheck=0
enabled=0
""",
                path="/etc/yum.repos.d/clusterhq-build.repo"),
            Run(command="yum install --enablerepo=clusterhq-build "
                        "-y clusterhq-flocker-node")
        ])

    def test_with_server(self):
        source = PackageSource(branch="branch",
                               build_server='http://nowhere.example/')
        commands = task_install_flocker(
            package_source=source,
            distribution="fedora-20")
        self.assertEqual(commands, [
            Run(command="yum install -y %s" % ZFS_REPO),
            Run(command="yum install -y %s" % CLUSTERHQ_REPO),
            Put(content="""\
[clusterhq-build]
name=clusterhq-build
baseurl=http://nowhere.example/results/omnibus/branch/fedora-20
gpgcheck=0
enabled=0
""",
                path="/etc/yum.repos.d/clusterhq-build.repo"),
            Run(command="yum install --enablerepo=clusterhq-build "
                        "-y clusterhq-flocker-node")
        ])

    def test_with_branch_and_version(self):
        source = PackageSource(branch="branch", version='0.3.2-693-g8ad1bda')
        commands = task_install_flocker(
            package_source=source,
            distribution="fedora-20")
        self.assertEqual(commands, [
            Run(command="yum install -y %s" % ZFS_REPO),
            Run(command="yum install -y %s" % CLUSTERHQ_REPO),
            Put(content="""\
[clusterhq-build]
name=clusterhq-build
baseurl=http://build.clusterhq.com/results/omnibus/branch/fedora-20
gpgcheck=0
enabled=0
""",
                path="/etc/yum.repos.d/clusterhq-build.repo"),
            Run(command="yum install --enablerepo=clusterhq-build "
                        "-y clusterhq-flocker-node-0.3.2-1.693.g8ad1bda")
        ])

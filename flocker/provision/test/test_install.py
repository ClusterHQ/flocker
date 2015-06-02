# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.provision._install``.
"""

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath

from pyrsistent import freeze

from ...acceptance.testtools import DatasetBackend
from .. import PackageSource
from .._install import (
    ManagedNode,
    task_install_flocker,
    task_enable_flocker_agent,
    configure_cluster,
    CLUSTERHQ_REPO,
    run, put,
)
from .._ca import Certificates

from .._effect import sequence


THE_AGENT_YML_PATH = b"/etc/flocker/agent.yml"
BASIC_AGENT_YML = freeze({
    "version": 1,
    "control-service": {
        "hostname": "192.0.2.42",
        "port": 4524,
    },
    "dataset": {
        "backend": "zfs",
    },
})


class ConfigureClusterTests(SynchronousTestCase):
    """
    Tests for ``configure_cluster``.
    """
    def test_enable_flocker_agent(self):
        """
        ``configure_cluster`` enables the Flocker agents with the storage
        driver and storage driver configuration passed to it.
        """
        control_node = ManagedNode(
            address="192.0.2.42", distribution="centos-7",
        )
        agent_node = ManagedNode(
            address="192.0.2.43", distribution="ubuntu-14.04",
        )
        dataset_backend = DatasetBackend.lookupByName("loopback")
        dataset_backend_configuration = dict(
            root_path="/foo/bar",
            compute_instance_id="baz-quux",
        )

        certificates_path = FilePath(self.mktemp())
        certificates_path.makedirs()
        for name in [
                b"cluster.crt", b"cluster.key",
                b"control-service.crt", b"control-service.key",
                b"user.crt", b"user.key",
                b"aaaaaaaa-aaaa-aaaa.crt", b"aaaaaaaa-aaaa-aaaa.key",
        ]:
            certificates_path.child(name).touch()

        commands = configure_cluster(
            control_node=control_node,
            agent_nodes=[],
            certificates=Certificates(certificates_path),
            dataset_backend=dataset_backend,
            dataset_backend_configuration=dataset_backend_configuration,
        )
        self.assertIn(
            task_enable_flocker_agent(
                distribution=agent_node.distribution,
                control_node=control_node.address,
                dataset_backend=dataset_backend,
                dataset_backend_configuration=dataset_backend_configuration,
            ).intent,
            list(effect.intent for effect in commands.intent.effects),
        )


class InstallFlockerTests(SynchronousTestCase):
    """
    Tests for ``task_install_flocker``.
    """

    def test_centos_no_arguments(self):
        """
        With no arguments, ``task_install_flocker`` installs the latest
        release.
        """
        distribution = 'centos-7'
        commands = task_install_flocker(distribution=distribution)
        self.assertEqual(commands, sequence([
            run(command="yum install -y %s" % CLUSTERHQ_REPO[distribution]),
            run(command="yum install -y clusterhq-flocker-node")
        ]))

    def test_centos_with_version(self):
        """
        With a ``PackageSource`` containing just a version,
        ``task_install_flocker`` installs that version from our release
        repositories.
        """
        distribution = 'centos-7'
        source = PackageSource(os_version="1.2.3-1")
        commands = task_install_flocker(
            package_source=source,
            distribution=distribution)
        self.assertEqual(commands, sequence([
            run(command="yum install -y %s" % CLUSTERHQ_REPO[distribution]),
            run(command="yum install -y clusterhq-flocker-node-1.2.3-1")
        ]))

    def test_ubuntu_no_arguments(self):
        """
        With no arguments, ``task_install_flocker`` installs the latest
        release.
        """
        distribution = 'ubuntu-14.04'
        commands = task_install_flocker(distribution=distribution)
        self.assertEqual(commands, sequence([
            run(command='apt-get -y install apt-transport-https software-properties-common'),  # noqa
            run(command='add-apt-repository -y ppa:james-page/docker'),
            run(command="add-apt-repository -y 'deb {} /'".format(CLUSTERHQ_REPO[distribution])),  # noqa
            run(command='apt-get update'),
            run(command='apt-get -y --force-yes install clusterhq-flocker-node'),  # noqa
        ]))

    def test_ubuntu_with_version(self):
        """
        With a ``PackageSource`` containing just a version,
        ``task_install_flocker`` installs that version from our release
        repositories.
        """
        distribution = 'ubuntu-14.04'
        source = PackageSource(os_version="1.2.3-1")
        commands = task_install_flocker(
            package_source=source,
            distribution=distribution)
        self.assertEqual(commands, sequence([
            run(command='apt-get -y install apt-transport-https software-properties-common'),  # noqa
            run(command='add-apt-repository -y ppa:james-page/docker'),
            run(command="add-apt-repository -y 'deb {} /'".format(CLUSTERHQ_REPO[distribution])),  # noqa
            run(command='apt-get update'),
            run(command='apt-get -y --force-yes install clusterhq-flocker-node=1.2.3-1'),  # noqa
        ]))

    def test_ubuntu_with_branch(self):
        """
        With a ``PackageSource`` containing just a branch,
        ``task_install_flocker`` installs that version from buildbot.
        """
        distribution = 'ubuntu-14.04'
        source = PackageSource(branch="branch-FLOC-1234")
        commands = task_install_flocker(
            package_source=source,
            distribution=distribution)
        self.assertEqual(commands, sequence([
            run(command='apt-get -y install apt-transport-https software-properties-common'),  # noqa
            run(command='add-apt-repository -y ppa:james-page/docker'),
            run(command="add-apt-repository -y 'deb {} /'".format(CLUSTERHQ_REPO[distribution])),  # noqa
            run(command="add-apt-repository -y "
                        "'deb http://build.clusterhq.com/results/omnibus/branch-FLOC-1234/ubuntu-14.04 /'"),  # noqa
            put(
                content='Package:  *\nPin: origin build.clusterhq.com\nPin-Priority: 900\n',  # noqa
                path='/etc/apt/preferences.d/buildbot-900'),
            run(command='apt-get update'),
            run(command='apt-get -y --force-yes install clusterhq-flocker-node'),  # noqa
        ]))

    def test_with_branch(self):
        """
        With a ``PackageSource`` containing just a branch,
        ``task_install_flocker`` installs the latest build of the branch from
        our build server.
        """
        distribution = 'centos-7'
        source = PackageSource(branch="branch")
        commands = task_install_flocker(
            package_source=source,
            distribution=distribution)
        self.assertEqual(commands, sequence([
            run(command="yum install -y %s" % CLUSTERHQ_REPO[distribution]),
            put(content="""\
[clusterhq-build]
name=clusterhq-build
baseurl=http://build.clusterhq.com/results/omnibus/branch/centos-7
gpgcheck=0
enabled=0
""",
                path="/etc/yum.repos.d/clusterhq-build.repo"),
            run(command="yum install --enablerepo=clusterhq-build "
                        "-y clusterhq-flocker-node")
        ]))

    def test_with_server(self):
        """
        With a ``PackageSource`` containing a branch and build server,
        ``task_install_flocker`` installs the latest build of the branch from
        that build server.
        """
        distribution = "centos-7"
        source = PackageSource(branch="branch",
                               build_server='http://nowhere.example/')
        commands = task_install_flocker(
            package_source=source,
            distribution=distribution)
        self.assertEqual(commands, sequence([
            run(command="yum install -y %s" % CLUSTERHQ_REPO[distribution]),
            put(content="""\
[clusterhq-build]
name=clusterhq-build
baseurl=http://nowhere.example/results/omnibus/branch/centos-7
gpgcheck=0
enabled=0
""",
                path="/etc/yum.repos.d/clusterhq-build.repo"),
            run(command="yum install --enablerepo=clusterhq-build "
                        "-y clusterhq-flocker-node")
        ]))

    def test_with_branch_and_version(self):
        """
        With a ``PackageSource`` containing a branch and version,
        ``task_install_flocker`` installs the specifed build of the branch from
        that build server.
        """
        distribution = "centos-7"
        source = PackageSource(branch="branch", os_version='1.2.3-1')
        commands = task_install_flocker(
            package_source=source,
            distribution=distribution)
        self.assertEqual(commands, sequence([
            run(command="yum install -y %s" % CLUSTERHQ_REPO[distribution]),
            put(content="""\
[clusterhq-build]
name=clusterhq-build
baseurl=http://build.clusterhq.com/results/omnibus/branch/centos-7
gpgcheck=0
enabled=0
""",
                path="/etc/yum.repos.d/clusterhq-build.repo"),
            run(command="yum install --enablerepo=clusterhq-build "
                        "-y clusterhq-flocker-node-1.2.3-1")
        ]))

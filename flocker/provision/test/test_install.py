# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.provision._install``.
"""

import yaml

from pyrsistent import freeze, thaw

from textwrap import dedent

from .._install import (
    task_configure_flocker_agent,
    task_enable_flocker_agent,
    run, put, run_from_args,
    get_repository_url, UnsupportedDistribution, get_installable_version,
    get_repo_options,
    _remove_dataset_fields, _remove_private_key,
    UnknownAction, DistributionNotSupported)
from .._ssh import Put
from .._effect import sequence
from ...acceptance.testtools import DatasetBackend
from ...testtools import TestCase

from ... import __version__ as flocker_version


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
    "logging": {
        "version": 1,
        "formatters": {
            "timestamped": {
                "datefmt": "%Y-%m-%d %H:%M:%S",
                "format": "%(asctime)s %(message)s"
            },
        },
    },
})


class ConfigureFlockerAgentTests(TestCase):
    """
    Tests for ``task_configure_flocker_agent``.
    """
    def test_agent_yml(self):
        """
        ```task_configure_flocker_agent`` writes a ``/etc/flocker/agent.yml``
        file which contains the backend configuration passed to it.
        """
        control_address = BASIC_AGENT_YML["control-service"]["hostname"]
        expected_pool = u"some-test-pool"
        expected_backend_configuration = dict(pool=expected_pool)
        commands = task_configure_flocker_agent(
            control_node=control_address,
            dataset_backend=DatasetBackend.lookupByName(
                BASIC_AGENT_YML["dataset"]["backend"]
            ),
            dataset_backend_configuration=expected_backend_configuration,
            logging_config=thaw(BASIC_AGENT_YML["logging"]),
        )
        [put_agent_yml] = list(
            effect.intent
            for effect in
            commands.intent.effects
            if isinstance(effect.intent, Put)
        )
        # Seems like transform should be usable here but I don't know how.
        expected_agent_config = BASIC_AGENT_YML.set(
            "dataset",
            BASIC_AGENT_YML["dataset"].update(expected_backend_configuration)
        )
        self.assertEqual(
            put(
                content=yaml.safe_dump(thaw(expected_agent_config)),
                path=THE_AGENT_YML_PATH,
                log_content_filter=_remove_dataset_fields,
            ).intent,
            put_agent_yml,
        )


class EnableFlockerAgentTests(TestCase):
    """
    Tests for ``task_enable_flocker_agent``.
    """
    def test_centos_sequence(self):
        """
        ``task_enable_flocker_agent`` for the 'centos-7' distribution returns
        a sequence of systemctl enable and start commands for each agent.
        """
        distribution = u"centos-7"
        commands = task_enable_flocker_agent(
            distribution=distribution,
        )
        expected_sequence = sequence([
            run(command="systemctl enable flocker-dataset-agent"),
            run(command="systemctl start flocker-dataset-agent"),
            run(command="systemctl enable flocker-container-agent"),
            run(command="systemctl start flocker-container-agent"),
        ])
        self.assertEqual(commands, expected_sequence)

    def test_centos_sequence_managed(self):
        """
        ``task_enable_flocker_agent`` for the 'centos-7' distribution
        returns a sequence of 'service restart' commands for each agent
        when the action passed down is "restart" (used for managed provider).
        """
        distribution = u"centos-7"
        commands = task_enable_flocker_agent(
            distribution=distribution,
            action="restart"
        )
        expected_sequence = sequence([
            run(command="systemctl enable flocker-dataset-agent"),
            run(command="systemctl restart flocker-dataset-agent"),
            run(command="systemctl enable flocker-container-agent"),
            run(command="systemctl restart flocker-container-agent"),
        ])
        self.assertEqual(commands, expected_sequence)

    def test_ubuntu_sequence(self):
        """
        ``task_enable_flocker_agent`` for the 'ubuntu-14.04' distribution
        returns a sequence of 'service start' commands for each agent.
        """
        distribution = u"ubuntu-14.04"
        commands = task_enable_flocker_agent(
            distribution=distribution,
        )
        expected_sequence = sequence([
            run(command="service flocker-dataset-agent start"),
            run(command="service flocker-container-agent start"),
        ])
        self.assertEqual(commands, expected_sequence)

    def test_ubuntu_sequence_managed(self):
        """
        ``task_enable_flocker_agent`` for the 'ubuntu-14.04' distribution
        returns a sequence of 'service restart' commands for each agent
        when the action passed down is "restart" (used for managed provider).
        """
        distribution = u"ubuntu-14.04"
        commands = task_enable_flocker_agent(
            distribution=distribution,
            action="restart"
        )
        expected_sequence = sequence([
            run(command="service flocker-dataset-agent restart"),
            run(command="service flocker-container-agent restart"),
        ])
        self.assertEqual(commands, expected_sequence)

    def test_sequence_invalid_action(self):
        """
        ``task_enable_flocker_agent`` for a valid distribution
        but an invalid action raises a ``UnknownAction``.
        """
        distribution = u"ubuntu-14.04"
        self.assertRaises(UnknownAction,
                          task_enable_flocker_agent,
                          distribution=distribution,
                          action="stop")

    def test_sequence_invalid_distro(self):
        """
        ``task_enable_flocker_agent`` for a non supported
        distribution raises a ``DistributionNotSupported``.
        """
        distribution = u"RedHat"
        self.assertRaises(DistributionNotSupported,
                          task_enable_flocker_agent,
                          distribution=distribution,
                          action="restart")


def _centos7_install_commands(version):
    """
    Construct the command sequence expected for installing Flocker on CentOS 7.

    :param str version: A Flocker native OS package version (a package name
        suffix) like ``"-1.2.3-1"``.

    :return: The sequence of commands expected for installing Flocker on
        CentOS7.
    """
    installable_version = get_installable_version(flocker_version)
    return sequence([
        run(command="yum clean all"),
        run(command="yum install -y {}".format(get_repository_url(
            distribution='centos-7',
            flocker_version=installable_version,
        ))),
        run_from_args(
            ['yum', 'install'] + get_repo_options(installable_version) +
            ['-y', 'clusterhq-flocker-node' + version])
    ])


class GetRepoOptionsTests(TestCase):
    """
    Tests for ``get_repo_options``.
    """

    def test_marketing_release(self):
        """
        No extra repositories are enabled if the latest installable version
        is a marketing release.
        """
        self.assertEqual(get_repo_options(flocker_version='0.3.0'), [])

    def test_development_release(self):
        """
        Enabling a testing repository is enabled if the latest installable
        version is not a marketing release.
        """
        self.assertEqual(
            get_repo_options(flocker_version='0.3.0.dev1'),
            ['--enablerepo=clusterhq-testing'])


class GetRepositoryURLTests(TestCase):
    """
    Tests for ``get_repository_url``.
    """

    def test_centos_7(self):
        """
        It is possible to get a repository URL for CentOS 7 packages.
        """
        expected = ("https://clusterhq-archive.s3.amazonaws.com/centos/"
                    "clusterhq-release$(rpm -E %dist).noarch.rpm")

        self.assertEqual(
            get_repository_url(
                distribution='centos-7',
                flocker_version='0.3.0'),
            expected
        )

    def test_ubuntu_14_04(self):
        """
        It is possible to get a repository URL for Ubuntu 14.04 packages.
        """
        expected = ("https://clusterhq-archive.s3.amazonaws.com/ubuntu/"
                    "$(lsb_release --release --short)/\\$(ARCH)")

        self.assertEqual(
            get_repository_url(
                distribution='ubuntu-14.04',
                flocker_version='0.3.0'),
            expected
        )

    def test_ubuntu_15_10(self):
        """
        It is possible to get a repository URL for Ubuntu 15.10 packages.
        """
        expected = ("https://clusterhq-archive.s3.amazonaws.com/ubuntu/"
                    "$(lsb_release --release --short)/\\$(ARCH)")

        self.assertEqual(
            get_repository_url(
                distribution='ubuntu-15.10',
                flocker_version='0.3.0'),
            expected
        )

    def test_unsupported_distribution(self):
        """
        An ``UnsupportedDistribution`` error is thrown if a repository for the
        desired distribution cannot be found.
        """
        self.assertRaises(
            UnsupportedDistribution,
            get_repository_url, 'unsupported-os', '0.3.0',
        )

    def test_non_release_ubuntu(self):
        """
        The operating system key for ubuntu has the suffix ``-testing`` for
        non-marketing releases.
        """
        expected = ("https://clusterhq-archive.s3.amazonaws.com/"
                    "ubuntu-testing/"
                    "$(lsb_release --release --short)/\\$(ARCH)")

        self.assertEqual(
            get_repository_url(
                distribution='ubuntu-14.04',
                flocker_version='0.3.0.dev1'),
            expected
        )

    def test_non_release_centos(self):
        """
        The operating system key for centos stays the same non-marketing
        releases.
        """
        expected = ("https://clusterhq-archive.s3.amazonaws.com/centos/"
                    "clusterhq-release$(rpm -E %dist).noarch.rpm")

        self.assertEqual(
            get_repository_url(
                distribution='centos-7',
                flocker_version='0.3.0.dev1'),
            expected
        )


class PrivateKeyLoggingTest(TestCase):
    """
    Test removal of private keys from logs.
    """

    def test_private_key_removed(self):
        """
        A private key is removed for logging.
        """
        key = dedent('''
            -----BEGIN PRIVATE KEY-----
            MFDkDKSLDDSf
            MFSENSITIVED
            MDKODSFJOEWe
            -----END PRIVATE KEY-----
            ''')
        self.assertEqual(
            dedent('''
                -----BEGIN PRIVATE KEY-----
                MFDk...REMOVED...OEWe
                -----END PRIVATE KEY-----
                '''),
            _remove_private_key(key))

    def test_non_key_kept(self):
        """
        Non-key data is kept for logging.
        """
        key = 'some random data, not a key'
        self.assertEqual(key, _remove_private_key(key))

    def test_short_key_kept(self):
        """
        A key that is suspiciously short is kept for logging.
        """
        key = dedent('''
            -----BEGIN PRIVATE KEY-----
            short
            -----END PRIVATE KEY-----
            ''')
        self.assertEqual(key, _remove_private_key(key))

    def test_no_end_key_removed(self):
        """
        A missing end tag does not prevent removal working.
        """
        key = dedent('''
            -----BEGIN PRIVATE KEY-----
            MFDkDKSLDDSf
            MFSENSITIVED
            MDKODSFJOEWe
            ''')
        self.assertEqual(
            '\n-----BEGIN PRIVATE KEY-----\nMFDk...REMOVED...OEWe\n',
            _remove_private_key(key))


class DatasetLoggingTest(TestCase):
    """
    Test removal of sensitive information from logged configuration files.
    """

    def test_dataset_logged_safely(self):
        """
        Values are either the same or replaced by 'REMOVED'.
        """
        config = {
            'dataset': {
                'secret': 'SENSITIVE',
                'zone': 'keep'
                }
            }
        content = yaml.safe_dump(config)
        logged = _remove_dataset_fields(content)
        self.assertEqual(
            yaml.safe_load(logged),
            {'dataset': {'secret': 'REMOVED', 'zone': 'keep'}})

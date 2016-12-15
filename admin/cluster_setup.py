# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Set up a Flocker cluster.
"""

import stat
import string
import sys
import yaml
from itertools import repeat
from pipes import quote as shell_quote

from eliot import FileDestination, write_failure
from pyrsistent import pvector
from txeffect import perform

from twisted.internet.defer import DeferredList, inlineCallbacks
from twisted.python.filepath import FilePath
from twisted.python.usage import UsageError

from .acceptance import (
    CLOUD_PROVIDERS,
    ClusterIdentity,
    CommonOptions,
    LibcloudRunner as OldLibcloudRunner,
    capture_journal,
    capture_upstart,
    configure_eliot_logging_for_acceptance,
    get_default_volume_size,
    get_trial_environment,
    save_backend_configuration,
)

from flocker.apiclient import FlockerClient
from flocker.common import loop_until
from flocker.control.httpapi import REST_API_PORT
from flocker.provision._ca import Certificates
from flocker.provision._common import Cluster
from flocker.provision._install import configure_control_node
from flocker.provision._ssh._conch import make_dispatcher


class LibcloudRunner(OldLibcloudRunner):
    """
    An alternative approach to setting up a cluster using
    a libcloud-compatible provisioner.
    """

    def _setup_control_node(self, reactor, node, index):
        print "Selecting node {} for control service".format(node.name)
        certificates = Certificates.generate(
            directory=self.cert_path,
            control_hostname=node.address,
            num_nodes=0,
            cluster_name=self.identity.name,
            cluster_id=self.identity.id,
        )
        dataset_backend_config_file = save_backend_configuration(
            self.dataset_backend, self.dataset_backend_configuration
        )
        cluster = Cluster(
            all_nodes=[node],
            control_node=node,
            agent_nodes=[],
            dataset_backend=self.dataset_backend,
            default_volume_size=get_default_volume_size(
                self.dataset_backend_configuration
            ),
            certificates=certificates,
            dataset_backend_config_file=dataset_backend_config_file
        )
        commands = configure_control_node(
            cluster,
            'libcloud',
            logging_config=self.config.get('logging'),
        )
        d = perform(make_dispatcher(reactor), commands)

        def configure_failed(failure):
            print "Failed to configure control node"
            write_failure(failure)
            return failure

        # It should be sufficient to configure just the control service here,
        # but there is an assumption that the control node is both a control
        # node and an agent node.
        d.addCallbacks(
            lambda _: self._add_node_to_cluster(
                reactor, cluster, node, index
            ),
            errback=configure_failed,
        )
        # Return the cluster.
        d.addCallback(lambda _: cluster)
        return d

    def _add_nodes_to_cluster(self, reactor, cluster, results):
        def add_node(node, index):
            # The control should be already fully configured.
            if node is not cluster.control_node:
                return self._add_node_to_cluster(reactor, cluster, node, index)

        for i, d in enumerate(results):
            d.addCallback(add_node, i)

        # Failure to add any one node to a cluster is not fatal,
        # we are happy with a partial success as long as we've
        # managed to configure the control node.
        # So, just wait until we are done with all nodes.
        d = DeferredList(results)
        d.addCallback(lambda _: cluster)
        return d

    def start_cluster(self, reactor):
        print "Assigning random tag:", self.random_tag
        names = []
        for index in range(self.num_nodes):
            name = self._make_node_name(self.random_tag, index)
            names.append(name)
        results = self._create_nodes(reactor, names)

        # Fire as soon as one node is provisioned,
        # this will be chosen as a control node.
        provisioning = DeferredList(results, fireOnOneCallback=True)

        def got_node_or_failed(value):
            if isinstance(value, list):
                # We've got a list with all failures.
                # This happens if none of the Deferreds resulted in success
                # while fireOnOneCallback is True.
                # Consume all the individual errbacks.
                for d in results:
                    d.addErrback(lambda _: None)
                # And return the first Failure.
                return value[0][1]

            (node, node_index) = value
            return (node, node_index)

        provisioning.addCallback(got_node_or_failed)
        provisioning.addCallback(
            lambda (node, index): self._setup_control_node(
                reactor,
                node,
                index
            )
        )
        provisioning.addCallback(
            lambda cluster: self._add_nodes_to_cluster(
                reactor,
                cluster,
                results
            )
        )

        def finalize_cluster(cluster):
            """
            :param Cluster cluster: Description of the cluster.
            :return: Cluster
            """
            # Make node lists immutable.
            return Cluster(
                all_nodes=pvector(cluster.all_nodes),
                control_node=cluster.node,
                agent_nodes=pvector(cluster.agent_nodes),
                dataset_backend=cluster.dataset_backend,
                default_volume_size=cluster.default_volume_size,
                certificates=cluster.certificates,
                dataset_backend_config_file=cluster.dataset_backend_config_file
            )

        provisioning.addCallback(finalize_cluster)

        return provisioning


class RunOptions(CommonOptions):
    description = "Set up a Flocker cluster."

    optParameters = [
        ['purpose', None, 'testing',
         "Purpose of the cluster recorded in its metadata where possible."],
        ['cert-directory', None, None,
         "Directory for storing the cluster certificates. "
         "If not specified, then a temporary directory is used."],
    ]

    optFlags = [
        ["no-keep", None, "Do not keep VMs around (when testing)"],
    ]

    synopsis = ('Usage: cluster-setup --distribution <distribution> '
                '[--provider <provider>]')

    def __init__(self, top_level):
        """
        :param FilePath top_level: The top-level of the Flocker repository.
        """
        super(RunOptions, self).__init__(top_level)
        # Override default values defined in the base class.
        self['provider'] = self.defaults['provider'] = 'aws'
        self['dataset-backend'] = self.defaults['dataset-backend'] = 'aws'

    def postOptions(self):
        self['purpose'] = unicode(self['purpose'])
        if any(x not in string.ascii_letters + string.digits + '-'
               for x in self['purpose']):
            raise UsageError(
                "Purpose may have only alphanumeric symbols and dash. " +
                "Found {!r}".format('purpose')
            )
        self._check_cert_directory()

        # This is run last as it creates the actual "runner" object
        # based on the provided parameters.
        super(RunOptions, self).postOptions()

    def _check_cert_directory(self):
        if self['cert-directory']:
            cert_path = FilePath(self['cert-directory'])
            _ensure_empty_directory(cert_path)
            self['cert-directory'] = cert_path

    def _make_cluster_identity(self, dataset_backend):
        purpose = self['purpose']
        return ClusterIdentity(
            purpose=purpose,
            prefix=purpose,
            name='{}-cluster'.format(purpose).encode("ascii"),
        )

    def _libcloud_runner(self, package_source, dataset_backend,
                         provider, provider_config):
        """
        Run some nodes using ``libcloud``.

        By default, two nodes are run.  This can be overridden by using
        the ``--number-of-nodes`` command line option.

        :param PackageSource package_source: The source of omnibus packages.
        :param BackendDescription dataset_backend: The description of the
            dataset backend the nodes are configured with.
        :param provider: The name of the cloud provider of nodes for the tests.
        :param provider_config: The ``managed`` section of the acceptance

        :returns: ``LibcloudRunner``.
        """
        if provider_config is None:
            self._provider_config_missing(provider)

        provisioner = CLOUD_PROVIDERS[provider](**provider_config)
        return LibcloudRunner(
            config=self['config'],
            top_level=self.top_level,
            distribution=self['distribution'],
            package_source=package_source,
            provisioner=provisioner,
            dataset_backend=dataset_backend,
            dataset_backend_configuration=self.dataset_backend_configuration(),
            variants=self['variants'],
            num_nodes=self['number-of-nodes'],
            identity=self._make_cluster_identity(dataset_backend),
            cert_path=self['cert-directory'],
        )


def _ensure_empty_directory(path):
    """
    The path should not exist or it should be an empty directory.
    If the path does not exist then a new directory is created.

    :param FilePath path: The directory path to check or create.
    """
    if path.exists():
        if not path.isdir():
            raise UsageError("{} is not a directory".format(path.path))
        if path.listdir():
            raise UsageError("{} is not empty".format(path.path))
        return

    try:
        path.makedirs()
        path.chmod(stat.S_IRWXU)
    except OSError as e:
        raise UsageError(
            "Can not create {}. {}: {}.".format(path.path, e.filename,
                                                e.strerror)
        )


def generate_managed_section(cluster):
    """
    Generate a managed configuration section for the given cluster.
    The section describes the nodes comprising the cluster.

    :param Cluster cluster: The cluster.
    :return: The managed configuration.
    :rtype: dict
    """
    addresses = list()
    for node in cluster.agent_nodes:
        if node.private_address is not None:
            addresses.append([node.private_address, node.address])
        else:
            addresses.append(node.address)
    return {
        "managed": {
            "addresses": addresses,
            "upgrade": True,
        }
    }


def create_managed_config(base_config, cluster):
    """
    Generate a full configuration from the given base configuration
    by adding a managed section for the given cluster instance.
    The base configuration should provide parameters like the dataset
    backend configurations and the cluster metadata.

    :param dict base_config: The base configuration.
    :param Cluster cluster: The cluster.
    :return: The new configuration with the managed section.
    :rtype: dict
    """
    config = dict(base_config)
    config.update(generate_managed_section(cluster))
    return config


def save_managed_config(directory, base_config, cluster):
    """
    Create and save a configuration file for the given cluster.
    The new configuration includes a managed section describing nodes
    of the cluster.

    :param FilePath directory: Directory where the new configuration is saved
        in a file named "managed.yaml".
    :param dict base_config: The base configuration.
    :param Cluster cluster: The cluster.
    """
    managed_config_file = directory.child("managed.yaml")
    managed_config = create_managed_config(base_config, cluster)
    managed_config_file.setContent(
        yaml.safe_dump(managed_config, default_flow_style=False)
    )


@inlineCallbacks
def main(reactor, args, base_path, top_level):
    """
    :param reactor: Reactor to use.
    :param list args: The arguments passed to the script.
    :param FilePath base_path: The executable being run.
    :param FilePath top_level: The top-level of the Flocker repository.
    """
    options = RunOptions(top_level=top_level)

    configure_eliot_logging_for_acceptance()
    try:
        options.parseOptions(args)
    except UsageError as e:
        sys.stderr.write("%s: %s\n" % (base_path.basename(), e))
        raise SystemExit(1)

    runner = options.runner

    def cluster_cleanup():
        print("stopping cluster")
        return runner.stop_cluster(reactor)

    cleanup_trigger_id = reactor.addSystemEventTrigger('before', 'shutdown',
                                                       cluster_cleanup)

    from flocker.common.script import eliot_logging_service
    log_writer = eliot_logging_service(
        destination=FileDestination(
            file=open("%s.log" % (base_path.basename(),), "a")
        ),
        reactor=reactor,
        capture_stdout=False)
    log_writer.startService()
    reactor.addSystemEventTrigger(
        'before', 'shutdown', log_writer.stopService)

    yield runner.ensure_keys(reactor)
    cluster = yield runner.start_cluster(reactor)

    save_managed_config(options['cert-directory'], options['config'], cluster)
    managed_config_file = options['cert-directory'].child("managed.yaml")
    managed_config = create_managed_config(options['config'], cluster)
    managed_config_file.setContent(
        yaml.safe_dump(managed_config, default_flow_style=False)
    )

    if options['distribution'] in ('centos-7',):
        remote_logs_file = open("remote_logs.log", "a")
        for node in cluster.all_nodes:
            capture_journal(reactor, node.address,
                            remote_logs_file).addErrback(write_failure)
    elif options['distribution'] in ('ubuntu-14.04',):
        remote_logs_file = open("remote_logs.log", "a")
        for node in cluster.all_nodes:
            capture_upstart(reactor, node.address,
                            remote_logs_file).addErrback(write_failure)

    flocker_client = make_client(reactor, cluster)
    yield wait_for_nodes(reactor, flocker_client, len(cluster.agent_nodes))

    if options['no-keep']:
        print("not keeping cluster")
    else:
        save_environment(
            options['cert-directory'], cluster, options.package_source()
        )
        reactor.removeSystemEventTrigger(cleanup_trigger_id)


def save_environment(directory, cluster, package_source):
    """
    Report environment variables describing the cluster.
    The variables are printed on standard output and also
    saved in "environment.env" file.

    :param FilePath directory: The variables are saved in this directory.
    :param Cluster cluster: The cluster.
    :param PackageSource package_source: The source of Flocker omnibus package.
    """
    environment_variables = get_trial_environment(cluster, package_source)
    environment_strings = list()
    for environment_variable in environment_variables:
        environment_strings.append(
            "export {name}={value};\n".format(
                name=environment_variable,
                value=shell_quote(
                    environment_variables[environment_variable]
                ),
            )
        )
    environment = ''.join(environment_strings)
    print("The following variables describe the cluster:")
    print(environment)
    env_file = directory.child("environment.env")
    env_file.setContent(environment)
    print("The variables are also saved in {}".format(
        env_file.path
    ))
    print("Be sure to preserve the required files.")


def make_client(reactor, cluster):
    """
    Create a :class:`FlockerClient` object for accessing the given cluster.

    :param reactor: The reactor.
    :param flocker.provision._common.Cluster cluster: The target cluster.
    :return: The client object.
    :rtype: flocker.apiclient.FlockerClient
    """
    control_node = cluster.control_node.address
    certificates_path = cluster.certificates_path
    cluster_cert = certificates_path.child(b"cluster.crt")
    user_cert = certificates_path.child(b"user.crt")
    user_key = certificates_path.child(b"user.key")
    return FlockerClient(reactor, control_node, REST_API_PORT,
                         cluster_cert, user_cert, user_key)


def wait_for_nodes(reactor, client, count):
    """
    Wait until nodes join the cluster.

    :param reactor: The reactor.
    :param flocker.apiclient.FlockerClient client: The client connected to
        the cluster (its control node).
    :param int count: The expected number of nodes in the cluster.
    :return: ``Deferred`` firing when the number of nodes in the cluster
        reaches the target.
    """

    def got_all_nodes():
        d = client.list_nodes()
        d.addErrback(write_failure)

        def check_node_count(nodes):
            print("Waiting for nodes, "
                  "got {} out of {}".format(len(nodes), count))
            return len(nodes) >= count

        d.addCallback(check_node_count)
        return d

    return loop_until(reactor, got_all_nodes, repeat(1, 120))

# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Set up a flocker cluster.
"""

import sys
import yaml
from pipes import quote as shell_quote

from eliot import (
    add_destination, FileDestination
)

from twisted.python.usage import Options, UsageError
from twisted.python.filepath import FilePath
from twisted.internet.defer import inlineCallbacks
from twisted.python.reflect import prefixedMethodNames

from admin.acceptance import (
    DISTRIBUTIONS,
    LibcloudRunner,
    ManagedRunner,
    VagrantRunner,
    capture_journal,
    capture_upstart,
    eliot_output,
    get_trial_environment,
)
from flocker.common import gather_deferreds
from flocker.provision import PackageSource, Variants, CLOUD_PROVIDERS
from flocker.acceptance.testtools import DatasetBackend


class RunOptions(Options):
    description = "Set up a flocker cluster."

    optParameters = [
        ['distribution', None, None,
         'The target distribution. '
         'One of {}.'.format(', '.join(DISTRIBUTIONS))],
        ['provider', None, 'aws',
         'The compute-resource provider to test against. '
         'One of {}.'],
        ['dataset-backend', None, 'aws',
         'The dataset backend to test against. '
         'One of {}'.format(', '.join(backend.name for backend
                                      in DatasetBackend.iterconstants()))],
        ['config-file', None, None,
         'Configuration for compute-resource providers and dataset backends.'],
        ['branch', None, None, 'Branch to grab packages from'],
        ['flocker-version', None, None, 'Version of flocker to install'],
        ['build-server', None, 'http://build.clusterhq.com/',
         'Base URL of build server for package downloads'],
        ['node-count', None, 2, 'Number of nodes to create (where applicable)',
         int],
    ]

    optFlags = [
        ["no-keep", None, "Do not keep VMs around (when testing)"],
    ]

    synopsis = ('Usage: cluster-setup --distribution <distribution> '
                '[--provider <provider>]')

    def __init__(self, top_level):
        """
        :param FilePath top_level: The top-level of the flocker repository.
        """
        Options.__init__(self)
        self.docs['provider'] = self.docs['provider'].format(
            self._get_provider_names()
        )
        self.top_level = top_level
        self['variants'] = []

    def _get_provider_names(self):
        """
        Find the names of all supported "providers" (eg Vagrant, Rackspace).

        :return: A ``list`` of ``str`` giving all such names.
        """
        return prefixedMethodNames(self.__class__, "_runner_")

    def opt_variant(self, arg):
        """
        Specify a variant of the provisioning to run.

        Supported variants: distro-testing, docker-head, zfs-testing.
        """
        self['variants'].append(Variants.lookupByValue(arg))

    def dataset_backend_configuration(self):
        """
        Get the configuration corresponding to storage driver chosen by the
        command line options.
        """
        drivers = self['config'].get('storage-drivers', {})
        configuration = drivers.get(self['dataset-backend'], {})
        return configuration

    def dataset_backend(self):
        """
        Get the storage driver the testing nodes will use.

        :return: A constant from ``DatasetBackend`` matching the name of the
            backend chosen by the command-line options.
        """
        configuration = self.dataset_backend_configuration()
        # Avoid requiring repetition of the backend name when it is the same as
        # the name of the configuration section.  But allow it so that there
        # can be "great-openstack-provider" and "better-openstack-provider"
        # sections side-by-side that both use "openstack" backend but configure
        # it slightly differently.
        dataset_backend_name = configuration.get(
            "backend", self["dataset-backend"]
        )
        try:
            return DatasetBackend.lookupByName(dataset_backend_name)
        except ValueError:
            raise UsageError(
                "Unknown dataset backend: {}".format(
                    dataset_backend_name
                )
            )

    def postOptions(self):
        if self['distribution'] is None:
            raise UsageError("Distribution required.")

        if self['config-file'] is not None:
            config_file = FilePath(self['config-file'])
            self['config'] = yaml.safe_load(config_file.getContent())
        else:
            self['config'] = {}

        provider = self['provider'].lower()
        provider_config = self['config'].get(provider, {})

        package_source = PackageSource(
            version=self['flocker-version'],
            branch=self['branch'],
            build_server=self['build-server'],
        )
        try:
            get_runner = getattr(self, "_runner_" + provider.upper())
        except AttributeError:
            raise UsageError(
                "Provider {!r} not supported. Available providers: {}".format(
                    provider, ', '.join(
                        name.lower() for name in self._get_provider_names()
                    )
                )
            )
        else:
            self.runner = get_runner(
                package_source=package_source,
                dataset_backend=self.dataset_backend(),
                provider_config=provider_config,
            )

    def _provider_config_missing(self, provider):
        """
        :param str provider: The name of the missing provider.
        :raise: ``UsageError`` indicating which provider configuration was
                missing.
        """
        raise UsageError(
            "Configuration file must include a "
            "{!r} config stanza.".format(provider)
        )

    def _runner_VAGRANT(self, package_source,
                        dataset_backend, provider_config):
        """
        :param PackageSource package_source: The source of omnibus packages.
        :param DatasetBackend dataset_backend: A ``DatasetBackend`` constant.
        :param provider_config: The ``vagrant`` section of the
            testing configuration file.  Since the Vagrant runner accepts no
            configuration, this is ignored.
        :returns: ``VagrantRunner``
        """
        return VagrantRunner(
            config=self['config'],
            top_level=self.top_level,
            distribution=self['distribution'],
            package_source=package_source,
            variants=self['variants'],
            dataset_backend=dataset_backend,
            dataset_backend_configuration=self.dataset_backend_configuration()
        )

    def _runner_MANAGED(self, package_source, dataset_backend,
                        provider_config):
        """
        :param PackageSource package_source: The source of omnibus packages.
        :param DatasetBackend dataset_backend: A ``DatasetBackend`` constant.
        :param provider_config: The ``managed`` section of the
            testing configuration file.  The section of the configuration
            file should look something like:

                managed:
                  addresses:
                    - "172.16.255.240"
                    - "172.16.255.241"
                  distribution: "centos-7"
        :returns: ``ManagedRunner``.
        """
        if provider_config is None:
            self._provider_config_missing("managed")

        if not provider_config.get("upgrade"):
            package_source = None

        return ManagedRunner(
            node_addresses=provider_config['addresses'],
            package_source=package_source,
            # TODO LATER Might be nice if this were part of
            # provider_config. See FLOC-2078.
            distribution=self['distribution'],
            dataset_backend=dataset_backend,
            dataset_backend_configuration=self.dataset_backend_configuration(),
        )

    def _libcloud_runner(self, package_source, dataset_backend,
                         provider, provider_config):
        """
        Run some nodes using ``libcloud``.

        By default, two nodes are run.  This can be overridden by setting
        ``FLOCKER_ACCEPTANCE_NUM_NODES`` in the environment.

        :param PackageSource package_source: The source of omnibus packages.
        :param DatasetBackend dataset_backend: A ``DatasetBackend`` constant.
        :param provider: The name of the cloud provider of nodes for the tests.
        :param provider_config: The appropriate section of the
            testing configuration file.

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
            num_nodes=self['node-count'],
        )

    def _runner_RACKSPACE(self, package_source, dataset_backend,
                          provider_config):
        """
        :param PackageSource package_source: The source of omnibus packages.
        :param DatasetBackend dataset_backend: A ``DatasetBackend`` constant.
        :param provider_config: The ``rackspace`` section of the
            testing configuration file.  The section of the configuration
            file should look something like:

               rackspace:
                 region: <rackspace region, e.g. "iad">
                 username: <rackspace username>
                 key: <access key>
                 keyname: <ssh-key-name>

        :see: :ref:`acceptance-testing-rackspace-config`
        """
        return self._libcloud_runner(
            package_source, dataset_backend, "rackspace", provider_config
        )

    def _runner_AWS(self, package_source, dataset_backend,
                    provider_config):
        """
        :param PackageSource package_source: The source of omnibus packages.
        :param DatasetBackend dataset_backend: A ``DatasetBackend`` constant.
        :param provider_config: The ``aws`` section of the testing
            configuration file.  The section of the configuration file should
            look something like:

               aws:
                 region: <aws region, e.g. "us-west-2">
                 zone: <aws zone, e.g. "us-west-2a">
                 access_key: <aws access key>
                 secret_access_token: <aws secret access token>
                 keyname: <ssh-key-name>
                 security_groups: ["<permissive security group>"]

        :see: :ref:`acceptance-testing-aws-config`
        """
        return self._libcloud_runner(
            package_source, dataset_backend, "aws", provider_config
        )


@inlineCallbacks
def main(reactor, args, base_path, top_level):
    """
    :param reactor: Reactor to use.
    :param list args: The arguments passed to the script.
    :param FilePath base_path: The executable being run.
    :param FilePath top_level: The top-level of the flocker repository.
    """
    options = RunOptions(top_level=top_level)

    add_destination(eliot_output)
    try:
        options.parseOptions(args)
    except UsageError as e:
        sys.stderr.write("%s: %s\n" % (base_path.basename(), e))
        raise SystemExit(1)

    runner = options.runner

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

    cluster = None
    results = []
    try:
        yield runner.ensure_keys(reactor)
        cluster = yield runner.start_cluster(reactor)
        if options['distribution'] in ('centos-7',):
            remote_logs_file = open("remote_logs.log", "a")
            for node in cluster.all_nodes:
                results.append(capture_journal(reactor,
                                               node.address,
                                               remote_logs_file)
                               )
        elif options['distribution'] in ('ubuntu-14.04', 'ubuntu-15.10'):
            remote_logs_file = open("remote_logs.log", "a")
            for node in cluster.all_nodes:
                results.append(capture_upstart(reactor,
                                               node.address,
                                               remote_logs_file)
                               )
        gather_deferreds(results)
        result = 0

    except Exception:
        result = 1
        raise
    finally:
        if options['no-keep']:
            runner.stop_cluster(reactor)
        else:
            if cluster is None:
                print("Didn't finish creating the cluster.")
            else:
                print("The following variables describe the cluster:")
                environment_variables = get_trial_environment(cluster)
                for environment_variable in environment_variables:
                    print("export {name}={value};".format(
                        name=environment_variable,
                        value=shell_quote(
                            environment_variables[environment_variable]),
                    ))
                print("Be sure to preserve the required files.")

    raise SystemExit(result)

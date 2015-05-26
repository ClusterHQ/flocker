# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Functionality for creating ``IBlockDeviceAPI`` providers suitable for use in
the current execution environment.

This depends on a ``FLOCKER_FUNCTIONAL_TEST_CLOUD_CONFIG_FILE`` environment
variable being set.

See `acceptance testing <acceptance-testing>`_ for details.

.. code-block:: python

    from .blockdevicefactory import ProviderType, get_blockdeviceapi

    api = get_blockdeviceapi(ProviderType.openstack)
    volume = api.create_volume(...)

"""

from os import environ
from uuid import uuid4
from functools import partial

from yaml import safe_load

from twisted.trial.unittest import SkipTest
from twisted.python.constants import Names, NamedConstant

from keystoneclient_rackspace.v2_0 import RackspaceAuth
from keystoneclient.session import Session

from cinderclient.client import Client as CinderClient
from novaclient.client import Client as NovaClient

from ..cinder import cinder_api
from ..ebs import EBSBlockDeviceAPI, ec2_client
from ..test.test_blockdevice import detach_destroy_volumes


class InvalidConfig(Exception):
    """
    The cloud configuration could not be found or is not compatible with the
    running environment.
    """


class ProviderType(Names):
    """
    Kinds of compute/storage cloud providers for which this module is able to
    build ``IBlockDeviceAPI`` providers.
    """
    openstack = NamedConstant()
    aws = NamedConstant()
    rackspace = NamedConstant()


def get_blockdeviceapi(provider):
    """
    Validate and load cloud provider's yml config file.
    Default to ``~/acceptance.yml`` in the current user home directory, since
    that's where buildbot puts its acceptance test credentials file.
    """
    cls, args = get_blockdeviceapi_args(provider)
    return cls(**args)


def get_blockdeviceapi_args(provider):
    """
    Get initializer arguments suitable for use in the instantiation of an
    ``IBlockDeviceAPI`` implementation compatible with the given provider.

    :param provider: A provider type the ``IBlockDeviceAPI`` is to be
        compatible with.  A value from ``ProviderType``.

    :raises: ``InvalidConfig`` if a
        ``FLOCKER_FUNCTIONAL_TEST_CLOUD_CONFIG_FILE`` was not set and the
        default config file could not be read.

    :return: A two-tuple of an ``IBlockDeviceAPI`` implementation and a
        ``dict`` of keyword arguments that can be used instantiate that
        implementation.
    """
    # ie cust0, rackspace, aws
    platform_name = environ.get('FLOCKER_FUNCTIONAL_TEST_CLOUD_PROVIDER')
    if platform_name is None:
        raise InvalidConfig(
            'Supply the platform on which you are running tests using the '
            'FLOCKER_FUNCTIONAL_TEST_CLOUD_PROVIDER environment variable.'
        )

    config_file_path = environ.get('FLOCKER_FUNCTIONAL_TEST_CLOUD_CONFIG_FILE')
    if config_file_path is None:
        raise InvalidConfig(
            'Supply the path to a cloud credentials file '
            'using the FLOCKER_FUNCTIONAL_TEST_CLOUD_CONFIG_FILE environment '
            'variable. See: '
            'https://docs.clusterhq.com/en/latest/gettinginvolved/acceptance-testing.html '  # noqa
            'for details of the expected format.'
        )

    with open(config_file_path) as config_file:
        config = safe_load(config_file.read())

    section = config.get(platform_name)
    if section is None:
        raise InvalidConfig(
            "The requested cloud platform "
            "was not found in the configuration file. "
            "Platform: %s, "
            "Configuration File: %s" % (platform_name, config_file_path)
        )

    provider_name = section.get('provider', platform_name)
    try:
        provider_environment = ProviderType.lookupByName(provider_name)
    except ValueError:
        raise InvalidConfig(
            "Unsupported provider. "
            "Supplied provider: %s, "
            "Available providers: %s" % (
                provider_name,
                ', '.join(p.name for p in ProviderType.iterconstants())
            )
        )

    if provider_environment != provider:
        raise InvalidConfig(
            "The requested cloud provider (%s) is not the provider running "
            "the tests (%s)." % (provider.name, provider_environment.name)
        )

    cls, get_kwargs = _BLOCKDEVICE_TYPES[provider]
    kwargs = dict(cluster_id=uuid4())
    kwargs.update(get_kwargs(**section))
    return cls, kwargs


from keystoneclient.auth import get_plugin_class


def _openstack_auth_from_config(**config):
    auth_plugin_name = config.pop('auth_plugin', 'password')

    if auth_plugin_name == 'rackspace':
        plugin_class = RackspaceAuth
    else:
        plugin_class = get_plugin_class(auth_plugin_name)

    plugin_options = plugin_class.get_options()
    plugin_kwargs = {}
    for option in plugin_options:
        # option.dest is the python compatible attribute name in the plugin
        # implementation.
        # option.dest is option.name with hyphens replaced with underscores.
        if option.dest in config:
            plugin_kwargs[option.dest] = config[option.dest]

    return plugin_class(**plugin_kwargs)


def _openstack(**config):
    """
    Create Cinder and Nova volume managers suitable for use in the creation of
    a ``CinderBlockDeviceAPI``.  They will be configured to use the region
    where the server that is running this code is running.

    :param config: Any additional configuration (possibly provider-specific)
        necessary to authenticate a session for use with the CinderClient and
        NovaClient.

    :return: A ``dict`` of keyword arguments for ``cinder_api``.
    """
    # The execution context should have set up this environment variable,
    # probably by inspecting some cloud-y state to discover where this code is
    # running.  Since the execution context is probably a stupid shell script,
    # fix the casing of the region name here (keystone is very sensitive to
    # case) instead of forcing me to figure out how to upper case things in
    # bash (I already learned a piece of shell syntax today, once is all I can
    # take).
    region = environ.get('FLOCKER_FUNCTIONAL_TEST_OPENSTACK_REGION')
    if region is not None:
        region = region.upper()
    auth = _openstack_auth_from_config(**config)
    session = Session(auth=auth)
    cinder_client = CinderClient(
        session=session, region_name=region, version=1
    )
    nova_client = NovaClient(
        session=session, region_name=region, version=2
    )
    return dict(
        cinder_client=cinder_client,
        nova_client=nova_client
    )


def _aws(**config):
    """
    Create an EC2 client suitable for use in the creation of an
    ``EBSBlockDeviceAPI``.

    :param bytes access_key: "access_key" credential for EC2.
    :param bytes secret_access_key: "secret_access_token" EC2 credential.
    """
    # We just get the credentials from the config file.
    # We ignore the region specified in acceptance test configuration,
    # and instead get the region from the zone of the host.
    zone = environ['FLOCKER_FUNCTIONAL_TEST_AWS_AVAILABILITY_ZONE']
    # The region is the zone, without the trailing [abc].
    region = zone[:-1]
    return {
        'ec2_client': ec2_client(
            region=region,
            zone=zone,
            access_key_id=config['access_key'],
            secret_access_key=config['secret_access_token'],
        ),
    }

# Map provider labels to IBlockDeviceAPI factory and a corresponding argument
# factory.
_BLOCKDEVICE_TYPES = {
    ProviderType.openstack: (cinder_api, _openstack),
    ProviderType.rackspace:
        (cinder_api, partial(_openstack, auth_plugin="rackspace")),
    ProviderType.aws: (EBSBlockDeviceAPI, _aws),
}

# ^^^^^^^^^^^^^^^^^^^^ generally useful implementation code, put it somewhere
# nice and use it
#
# https://clusterhq.atlassian.net/browse/FLOC-1840
#
# vvvvvvvvvvvvvvvvvvvv testing helper that actually belongs in this module


def get_blockdeviceapi_with_cleanup(test_case, provider):
    """
    Instantiate an ``IBlockDeviceAPI`` implementation appropriate to the given
    provider and configured to work in the current environment.  Arrange for
    all volumes created by it to be cleaned up at the end of the current test
    run.

    :param TestCase test_case: The running test.
    :param provider: A provider type the ``IBlockDeviceAPI`` is to be
        compatible with.  A value from ``ProviderType``.

    :raises: ``SkipTest`` if either:
        1) A ``FLOCKER_FUNCTIONAL_TEST_CLOUD_CONFIG_FILE``
        was not set and the default config file could not be read, or,
        2) ``FLOCKER_FUNCTIONAL_TEST`` environment variable was unset.

    :return: The new ``IBlockDeviceAPI`` provider.
    """
    flocker_functional_test = environ.get('FLOCKER_FUNCTIONAL_TEST')
    if flocker_functional_test is None:
        raise SkipTest(
            'Please set FLOCKER_FUNCTIONAL_TEST environment variable to '
            'run storage backend functional tests.'
        )

    try:
        api = get_blockdeviceapi(provider)
    except InvalidConfig as e:
        raise SkipTest(str(e))
    test_case.addCleanup(detach_destroy_volumes, api)
    return api

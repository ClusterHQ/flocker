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

from yaml import safe_load

from twisted.trial.unittest import SkipTest
from twisted.python.constants import Names, NamedConstant

from keystoneclient_rackspace.v2_0 import RackspaceAuth
from keystoneclient.session import Session

from cinderclient.client import Client as CinderClient
from novaclient.client import Client as NovaClient

from ..cinder import CinderBlockDeviceAPI
from ..ebs import EBSBlockDeviceAPI, ec2_client
from ..test.test_blockdevice import detach_destroy_volumes


# The Rackspace authentication endpoint
# See http://docs.rackspace.com/cbs/api/v1.0/cbs-devguide/content/Authentication-d1e647.html # noqa
RACKSPACE_AUTH_URL = "https://identity.api.rackspacecloud.com/v2.0"


class InvalidConfig(Exception):
    """
    The cloud configuration could not be found, or is not compatible with the
    running environment.
    """


class ProviderType(Names):
    """
    Kinds of compute/storage cloud providers for which this module is able to
    build ``IBlockDeviceAPI`` providers.
    """
    openstack = NamedConstant()
    aws = NamedConstant()


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
    provider_env_name = environ.get('FLOCKER_FUNCTIONAL_TEST_CLOUD_PROVIDER')
    if provider_env_name is None:
        raise InvalidConfig(
            'Supply the provider running tests using the '
            'FLOCKER_FUNCTIONAL_TEST_CLOUD_PROVIDER envionment variable.'
        )

    provider_env = ProviderType.lookupByName(provider_env_name)
    if provider_env != provider:
        raise InvalidConfig(
            "The requested cloud provider (%s) is not the provider running "
            "the tests (%s)." % (provider.name, provider_env.name)
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

    section = config[provider.name]
    cls, get_kwargs = _BLOCKDEVICE_TYPES[provider]
    kwargs = dict(cluster_id=uuid4())
    kwargs.update(get_kwargs(**section))
    return cls, kwargs


def _rackspace_session(username, key, **kwargs):
    """
    Create a Keystone session capable of authenticating with Rackspace.

    :param unicode keyname: A RackSpace API username.
    :param unicode key: A RackSpace API key.

    :return: A ``keystoneclient.session.Session``.
    """
    auth = RackspaceAuth(
        auth_url=RACKSPACE_AUTH_URL,
        username=username,
        api_key=key
    )
    return Session(auth=auth)


def _openstack(region, **config):
    """
    Create Cinder and Nova volume managers suitable for use in the creation of
    a ``CinderBlockDeviceAPI``.

    :param bytes region: The name of the region to which to connect.
    :param config: Any additional configuration (possibly provider-specific)
        necessary to authenticate a session for use with the CinderClient and
        NovaClient.

    :return: A ``dict`` giving initializer arguments for
        ``CinderBlockDeviceAPI``.
    """
    # TODO: Look up the right session factory in the config and use it here
    # instead of assuming Rackspace.
    session = _rackspace_session(**config)
    cinder_client = CinderClient(
        session=session, region_name=region, version=1
    )
    nova_client = NovaClient(
        session=session, region_name=region, version=2
    )
    return dict(
        cinder_volume_manager=cinder_client.volumes,
        nova_volume_manager=nova_client.volumes,
    )


def _aws(**config):
    """
    Create an EC2 client suitable for use in the creation of an
    ``EBSBlockDeviceAPI``.

    :param bytes access_key: "access_key" credential for EC2.
    :param str secret_access_key: "secret_access_token" EC2 credential.
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


_BLOCKDEVICE_TYPES = {
    ProviderType.openstack: (CinderBlockDeviceAPI, _openstack),
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

    :raises: ``SkipTest`` if a ``FLOCKER_FUNCTIONAL_TEST_CLOUD_CONFIG_FILE``
        was not set and the default config file could not be read.

    :return: The new ``IBlockDeviceAPI`` provider.
    """
    try:
        api = get_blockdeviceapi(provider)
    except InvalidConfig as e:
        raise SkipTest(str(e))
    test_case.addCleanup(detach_destroy_volumes, api)
    return api

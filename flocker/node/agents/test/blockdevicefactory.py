from os import environ
from uuid import uuid4

from yaml import safe_load

from twisted.trial.unittest import SkipTest

from ..cinder import CinderBlockDeviceAPI
from ..ebs import EBSBlockDeviceAPI, ec2_client


_BLOCKDEVICETYPES = {
    "rackspace": CinderBlockDeviceAPI,
    #    "pistoncloud": CinderBlockDeviceAPI,
    "aws": EBSBlockDeviceAPI,
}


from ..test.test_blockdevice import detach_destroy_volumes


def get_blockdeviceapi(provider):
    """
    Validate and load cloud provider's yml config file.
    Default to ``~/acceptance.yml`` in the current user home directory, since
    that's where buildbot puts its acceptance test credentials file.

    :raises: ``SkipTest`` if a ``CLOUD_CONFIG_FILE`` was not set and the
        default config file could not be read.
    """
    args = get_blockdevice_args(provider)
    return _BLOCKDEVICETYPES[provider](**args)


def get_blockdevice_args(provider):
    config_file_path = environ.get('CLOUD_CONFIG_FILE')
    if config_file_path is not None:
        config_file = open(config_file_path)
    else:
        # Raise a different exception
        raise SkipTest(
            'Supply the path to a cloud credentials file '
            'using the CLOUD_CONFIG_FILE environment variable. '
            'See: '
            'https://docs.clusterhq.com/en/latest/gettinginvolved/acceptance-testing.html '  # noqa
            'for details of the expected format.'
        )
    config = safe_load(config_file.read())
    section = config[provider]
    return _BLOCKDEVICEAPIS[provider](section)


from keystoneclient_rackspace.v2_0 import RackspaceAuth
from keystoneclient.session import Session

from cinderclient.client import Client as CinderClient
from novaclient.client import Client as NovaClient

# The Rackspace authentication endpoint
# See http://docs.rackspace.com/cbs/api/v1.0/cbs-devguide/content/Authentication-d1e647.html # noqa
RACKSPACE_AUTH_URL = "https://identity.api.rackspacecloud.com/v2.0"


def rackspace_session(**kwargs):
    """
    Create a Keystone session capable of authenticating with Rackspace.

    :param unicode username: A RackSpace API username.
    :param unicode api_key: A RackSpace API key.
    :param unicode region: A RackSpace region slug.
    :return: A ``keystoneclient.session.Session``.
    """
    username = kwargs.pop('username')
    api_key = kwargs.pop('key')

    auth = RackspaceAuth(
        auth_url=RACKSPACE_AUTH_URL,
        username=username,
        api_key=api_key
    )
    return Session(auth=auth)


def rackspace(config):
    region_slug = config.pop("region")
    session = rackspace_session(**config)
    cinder_client = CinderClient(
        session=session, region_name=region_slug, version=1
    )
    nova_client = NovaClient(
        session=session, region_name=region_slug, version=2
    )
    cluster_id = uuid4()
    return dict(
        cinder_client=cinder_client,
        nova_client=nova_client,
        cluster_id=cluster_id,
    )


def aws(config):
    cluster_id = uuid4()
    return dict(
        ec2_client=ec2_client(**config),
        cluster_id=cluster_id,
    )


_BLOCKDEVICEAPIS = {
    "rackspace": rackspace,
    #    "pistoncloud": pistoncloud,
    "aws": aws,
}


# ^^^^^^^^^^^^^^^^^^^^ generally useful implementation code, put it somewhere
# nice and use it
#
#
# vvvvvvvvvvvvvvvvvvvv testing helper that actually belongs in this module

def get_blockdeviceapi_with_cleanup(test_case, provider):
    """
    Validate and load cloud provider's yml config file.
    Default to ``~/acceptance.yml`` in the current user home directory, since
    that's where buildbot puts its acceptance test credentials file.

    :raises: ``SkipTest`` if a ``CLOUD_CONFIG_FILE`` was not set and the
        default config file could not be read.
    """
    # Handle the exception raised by get_blockdeviceapi_args and turn it into a
    # skip test
    api = get_blockdeviceapi(provider)
    test_case.addCleanup(detach_destroy_volumes, api)
    return api

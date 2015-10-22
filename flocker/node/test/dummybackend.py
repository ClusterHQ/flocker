"""
A dummy backend plugin for flocker-dataset-agent.
"""

from twisted.python.filepath import FilePath

from flocker.node import BackendDescription, DeployerType
from flocker.node.agents.blockdevice import LoopbackBlockDeviceAPI

DUMMY_API = LoopbackBlockDeviceAPI(FilePath(b"/tmp/foo"), u"")


def api_factory(cluster_id, **kwargs):
    """
    Factory for ``IBlockDeviceAPI``.

    :return: ``LoopbackBlockDeviceAPI`` instance.
    """
    # We get custom arguments from /etc/flocker/agent.yml's backend
    # section:
    if kwargs != {"custom": u"arguments!"}:
        raise AssertionError("Didn't get correct arguments passed in")
    # A real implementation would create new IBlockDeviceAPI and return it
    # here, based on the given arguments:
    return DUMMY_API


# The backend provided by this plugin:
FLOCKER_BACKEND = BackendDescription(
    name=u"dummybackend",  # Not actually used for 3rd party plugins
    needs_reactor=False, needs_cluster_id=True,
    api_factory=api_factory, deployer_type=DeployerType.block)

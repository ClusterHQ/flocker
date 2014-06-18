# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from twisted.internet.endpoints import ProcessEndpoint
from twisted.internet.defer import Deferred, gatherResults
from twisted.protocols.basic import NetstringReceiver
from twisted.internet import reactor

from yaml import safe_load, safe_dump


class _SendConfiguration(NetstringReceiver):
    def __init__(self, configuration):
        self.configuration = configuration
        self.result = Deferred()

    def connectionMade(self):
        self.sendString(safe_dump(self.configuration))

    def stringReceived(self, data):
        if data == "success":
            self.result.callback(None)
        else:
            self.result.errback(Exception(data))
        self.transport.loseConnection()


def _node_directed_deploy(desired_configuration):
    """
    A deployment strategy which delegates all of the hard work to the
    individual nodes.

    Specifically, contact each node mentioned in ``desired_configuration`` and
    tell it what the cluster-wide desired configuration is.  Let each node
    figure out what changes need to be made on that node and then make them
    itself.
    """
    return gatherResults(
        _node_directed_single_deploy(node, desired_configuration)
        for node in desired_configuration)


deploy = _node_directed_deploy


def _node_directed_single_deploy(node, desired_configuration):
    """
    Contact the specified node and tell it to change its configuration to match
    ``desired_configuration``.

    :param Node: node:
    """
    protocol = _SendConfiguration(desired_configuration)
    endpoint = ProcessEndpoint(reactor, b"ssh", b"flocker-node", b"--deploy")

    #
    # XXX What if this connection is lost after the configuration is sent but
    # before the result is received?  Need to make it possible to reconnect and
    # get the results of a previous deploy attempt.
    #
    # deploy is idempotent!  just retry.  it doesn't hurt to do the same deploy
    # twice.  if the first one succeeded then the second one will instantly
    # succeed.  if the first one failed then the second one will make progress
    # or fail the same way.
    # 
    connecting = endpoint.connect(protocol)
    connecting.addCallback(lambda ignored: protocol.result)
    return connecting


def main(application_config_path, deployment_config_path):
    return deploy({
            u"application": safe_load(application_config_path),
            u"deployment": safe_load(deployment_config_path),
            })

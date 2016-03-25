# Need to add the specified key to the ssh agent
# -- or use it to connect if that's possible??




import sys

from pyrsistent import PClass, field
from eliot import FileDestination
from zope.interface import implementer
from twisted.python.usage import Options, UsageError
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.defer import Deferred

from txeffect import perform
from flocker.provision._ssh import (
    run, run_remotely
)

from flocker.node import DeployerType, BackendDescription
from flocker.provision._ssh._conch import make_dispatcher
from flocker.provision._effect import sequence
from flocker.provision._common import Cluster
from flocker.provision._ca import Certificates
from flocker.common.script import eliot_logging_service
from flocker.provision._common import INode
from .acceptance import (
    configure_eliot_logging_for_acceptance,
)



@implementer(INode)
class ManagedNode(PClass):
    """
    A node managed by some other system (eg by hand or by another
    piece of orchestration software).
    """
    address = field(type=bytes, mandatory=True)
    private_address = field(type=(bytes, type(None)),
                            initial=None, mandatory=True)
    distribution = field(type=bytes, mandatory=True)
    username = field(type=bytes, mandatory=False)


class RunOptions(Options):
    description = "Provision a Flocker cluster."

    optParameters = [
        ['user', None, None, ""],
        ['identity', None, None, ""],
        ['agent-config', None, None, ""],
        ['control-node', None, None, ""],
        ['agent-nodes', None, None, ""],
        ['cluster-name', None, None, ""], # optional
        ['cluster-id', None, None, ""], # optional
        ['cert-directory', None, None,
         "Directory for storing the cluster certificates. "
         "If not specified, then a temporary directory is used."],
    ]
    optFlags = [
        ['install-flocker',],
        ['install-flocker-docker-plugin',],
        ['no-certs',],
        ['force'],
    ]



#from flocker.provision._common import PackageSource
from flocker.provision._install import (
    task_install_flocker,
    _run_on_all_nodes
)

def install_flocker(cluster):
    """
    Todo: if flocker exists on the node, uninstall flocker first
    """
    _run_on_all_nodes(
        cluster.all_nodes,
        task=lambda node: task_install_flocker(
            distribution=node.distribution,
        )
    )


def install_flocker_docker_plugin(cluster):
    _run_on_all_nodes(
        cluster.all_nodes,
        task=lambda node: task_install_flocker(
            distribution=node.distribution,
        )
    )


def distribute_certs(cluster, options):
    # create the certs locally
    # distribute to the nodes
    # need to have the user specify the api cert name...
    pass


def print_install_plan(cluster, options):
    user_message = []
    if (options['install-flocker'] or
        options['install-flocker-docker-plugin']):
        user_message.append("The following items will be installed")
        if options['install-flocker']:
            user_message.append("  * flocker")
        if options['install-flocker-docker-plugin']:
            user_message.append("  * flocker-docker-plugin")
    if options['no-certs']:
        user_message.append("No certificates will be distributed to the nodes")
    else:
        user_message.append(
            "New certificates will be distributed to the nodes")
    user_message.append("Cluster")
    user_message.append("-------")
    user_message.append("Control Node:")
    user_message.append("  - {}".format(str(cluster.control_node.address)))
    user_message.append("Agent Nodes:")
    for node in cluster.agent_nodes:
        user_message.append("  - {}".format(str(node.address)))
    for line in user_message:
        print(line)


def prompt_user_for_continue():
    answer = raw_input("Do you want to continue? [Y/n]")
    if not answer.tolower() == 'y':
        print("Abort.")
        sys.exit(1)


# def ensure_keys(self, reactor):
#     # ensure we have the private key for the provided key
#     key = get_ssh_key()
#     if key is not None:
#         return ensure_agent_has_ssh_key(reactor, key)
#     else:
#         return succeed(None)


def get_node_distro(reactor, host, username, d):
    perform(
        make_dispatcher(reactor),
        run_remotely(
            username=username,
            address=host,
            commands=sequence([
                run('grep ubuntu /etc/os-release').on(
                    success=lambda v: d.callback('ubuntu'),
                    error=lambda v: d.callback('centos'),
                )
            ])
        )
    )


def create_node(reactor, ip_address, username):
    def node_factory(distro):
        return ManagedNode(
            address=ip_address,
            username=username,
            distribution=distro
        )
    distro_query = Deferred()
    distro_query.addCallback(node_factory)
    get_node_distro(reactor, ip_address, username, distro_query)
    return distro_query


def get_certificates(options, control_node, agent_nodes):
    return Certificates.generate(
        directory=options['cert-directory'],
        control_hostname=control_node.address,
        num_nodes=len(agent_nodes),
        cluster_name=options['cluster-name'],
        cluster_id=options['cluster-id']
    )


@inlineCallbacks
def create_cluster(reactor, username,
                   control_node_address, agent_node_addresses,
                   dataset_backend, agent_yaml_path):
    # todo, do this in parallel without inline callbacks
    control_node = yield create_node(reactor, control_node_address, username)
    agent_nodes = []
    for node_address in agent_node_addresses:
        agent_node = yield create_node(reactor, node_address, username)
        agent_nodes.append(agent_node)
    if control_node_address in agent_node_addresses:
        all_nodes = agent_nodes
    else:
        all_nodes = [control_node] + agent_nodes
    #certificates = get_certificates(control_node, agent_nodes)
    cluster = Cluster(
        all_nodes=all_nodes,
        control_node=control_node,
        agent_nodes=agent_nodes,
        dataset_backend=get_backend_description(),
        default_vlume_size=10,
        certificates=get_certificates(control_node, agent_node),
        dataset_backend_config_file=agent_yaml_path
    )
    yield returnValue(cluster)


def get_backend_description(options):
    return BackendDescription(name=options['cluster-name'],
                              needs_reactor=True,
                              needs_cluster_id=True,
                              api_factory=None,
                              deployer_type=DeployerType.block)

@inlineCallbacks
def run_provisioning(cluster, actions):
    print "We need to do: "
    for action in actions:
        print action


@inlineCallbacks
def main(reactor, args, base_path, top_level):
    options = RunOptions(top_level=top_level)
    configure_eliot_logging_for_acceptance()
    try:
        options.parseOptions(args)
    except UsageError as e:
        sys.stderr.write("%s: %s\n" % (base_path.basename(), e))
        raise SystemExit(1)

    log_writer = eliot_logging_service(
        destination=FileDestination(
            file=open("%s.log" % (base_path.basename(),), "a")
        ),
        reactor=reactor,
        capture_stdout=False)
    log_writer.startService()
    reactor.addSystemEventTrigger(
        'before', 'shutdown', log_writer.stopService)

    # todo, implement this
    #ensure_keys()
    cluster = create_cluster(options)
    actions = []
    if options['install-flocker']:
        actions.append(install_flocker)
    if options['install-flocker-docker-plugin']:
        actions.append(install_flocker_docker_plugin)
    if not options['no-certs']:
        actions.append(distribute_certs)
    print_install_plan()
    if not options['force']:
        prompt_user_for_continue()
    run_provisioning(cluster, actions)

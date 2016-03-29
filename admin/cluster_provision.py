
# Todo:
# Need to add the specified key to the ssh agent
# -- or use it to connect if that's possible??
# -- what if the user doesn't have an ssh agent running?
# need to have the command line option of specifying the api cert name
# if flocker exists on the node, uninstall flocker first
# if agent_config_filepath isn't specified don't distribute it to the nodes?

import sys
from functools import partial
import tempfile
import yaml

from pyrsistent import PClass, field
from eliot import FileDestination
from zope.interface import implementer
from twisted.python.usage import Options, UsageError
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.defer import Deferred
from twisted.python.filepath import FilePath

from effect import parallel
from txeffect import perform

#from flocker.provision._common import PackageSource
from flocker.provision._install import (
    task_install_flocker,
    _run_on_all_nodes,
    _remove_dataset_fields,
    task_install_control_certificates,
    task_install_node_certificates,
    task_install_api_certificates,
)
from flocker.provision._ssh import (
    run, run_remotely, sudo_put
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

    def get_default_username(self):
        return self.username


class RunOptions(Options):
    description = "Provision a Flocker cluster."

    optParameters = [
        ['user', 'u', 'ubuntu', ""],
        ['identity', 'i', None, ""],
        ['agent-config', None, '/home/bcox/config_files/agent.yml', ""],
        ['control-node', None, 'ec2-52-38-69-204.us-west-2.compute.amazonaws.com', ""],
        ['agent-nodes', None, 'ec2-52-38-69-204.us-west-2.compute.amazonaws.com', ""],
        ['cluster-name', None, u'mycluster', ""], # optional
        ['cluster-id', None, None, ""], # optional
        ['cluster-file', None, None, ""], # optional
        ['cert-directory', None, None,
         "Directory for storing the cluster certificates. "
         "If not specified, then a temporary directory is used."],
    ]

    optFlags = [
        ['install-flocker', None, ""],
        ['install-flocker-docker-plugin', None, ""],
        ['no-certs', None, ""],
        ['force', None, ""],
    ]

def get_nodes(options):
    def bad_config(msg):
        print msg
        sys.exit(1)

    def parse_cluster_file(filepath):
        cluster_nodes_filepath = FilePath(filepath)
        config = yaml.safe_load(cluster_nodes_filepath.getContent())
        if 'control_service' not in config:
            print "cluster-file must contain a control_service attribute"
            sys.exit(1)
        if 'agents' not in config:
            print "cluster-file must contain an agents attribute"
            sys.exit(1)

        # todo, make sure control_service is a stringtype
        # and that agents is a list of strings or something
        # like that (if it's a dict, get the keys)
        return config['control_service'], config['agents']

    def parse_node_list(nodes_str):
        return [node.strip()
                for node in nodes_str.split(',')
                if node.strip()]

    if options['control-node'] and options['cluster-file']:
        bad_config(
            "Error: You cannot specify both a cluster-file and control-node")
    elif options['agent-nodes'] and options['cluster-file']:
        bad_config(
            "Error: You cannot specify both a cluster-file and agent-nodes")
    if options['cluster-file']:
        return parse_cluster_file(options['cluster-file'])
    else:
        return options['control-node'], parse_node_list(options['agent-nodes'])


def install_flocker(cluster):
    # Todo: if flocker exists on the node, uninstall flocker first
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
    # need to have the user specify the api cert name...
    import pdb; pdb.set_trace()
    control_command = run_remotely(
        username=cluster.control_node.get_default_username(),
        address=cluster.control_node.address,
        commands=sequence([
        task_install_control_certificates(
            cluster.certificates.cluster.certificate,
            cluster.certificates.control.certificate,
            cluster.certificates.control.key),
        ])
    )

    node_commands = []
    for certnkey, node in zip(cluster.certificates.nodes,
                              cluster.agent_nodes):
        cmd = run_remotely(
            username=node.get_default_username(),
            address=node.address,
            commands=sequence([
                task_install_node_certificates(
                    cluster.certificates.cluster.certificate,
                    # todo, get the right cert from the node
                    certnkey.certificate,
                    certnkey.key),
                task_install_api_certificates(
                    cluster.certificates.user.certificate,
                    cluster.certificates.user.key)
            ])
        )
        node_commands.append(cmd)
        parallel_node_commands = parallel(node_commands)
    return sequence([control_command, parallel_node_commands])


def distribute_agent_yaml(cluster):
    content = cluster.dataset_backend_config_file.getContent()
    put_config_file = sudo_put(
        path='/etc/flocker/agent.yml',
        content=content,
        log_content_filter=_remove_dataset_fields
    )
    # todo new function run_on_nodes?
    return parallel(list(
        run_remotely(
            username=node.get_default_username(),
            address=node.address,
            commands=put_config_file,
        )
        for node in cluster.agent_nodes
    ))


def post_install_actions():
    # TODO:
    # if we installed flocker, enable the service and
    # also open ports on firewall (if enabled)
    #
    # restart services
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
    user_message.append("  - {} ({})".format(
        str(cluster.control_node.address), cluster.control_node.distribution))
    user_message.append("Agent Nodes:")
    for node in cluster.agent_nodes:
        user_message.append("  - {} ({})".format(
            str(node.address), node.distribution))
    print("")
    for line in user_message:
        print(line)


def prompt_user_for_continue():
    answer = raw_input("Do you want to continue? [Y/n]")
    if not answer.lower() == 'y':
        print("Abort.")
        sys.exit(1)


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


def create_cert_directory(options):
    directory = None
    if options['cert-directory']:
        directory = FilePath(options['cert-directory'])
        if not directory.exists():
            directory.makedirs()
        elif not directory.isdir():
            print("Certificate directory exists but is not a directory")
            sys.exit(1)
    else:
        dir_prefix = '{}_'.format(options['cluster-name'])
        directory = FilePath(tempfile.mkdtemp(prefix=dir_prefix))
        print("New cluster certs will be created in {}".format(
            str(directory.realpath())))
    assert directory, "Directory should not be None"
    return directory


def get_certificates(options, control_node, agent_nodes):
    directory = create_cert_directory(options)
    return Certificates.generate(
        directory=directory,
        control_hostname=control_node.address,
        num_nodes=len(agent_nodes),
        cluster_name=options['cluster-name'],
        cluster_id=options['cluster-id']
    )


def get_backend_description(options):
    return BackendDescription(name=options['cluster-name'],
                              needs_reactor=True,
                              needs_cluster_id=True,
                              api_factory=None,
                              deployer_type=DeployerType.block)


@inlineCallbacks
def create_cluster(reactor, options,
                   control_node_address, agent_node_addresses,
                   agent_config_filepath):
    # todo, do this in parallel without inline callbacks
    username = options['user']
    control_node = yield create_node(reactor, control_node_address, username)
    agent_nodes = []
    for node_address in agent_node_addresses:
        agent_node = yield create_node(reactor, node_address, username)
        agent_nodes.append(agent_node)
    if control_node_address in agent_node_addresses:
        all_nodes = agent_nodes
    else:
        all_nodes = [control_node] + agent_nodes
    cluster = Cluster(
        all_nodes=all_nodes,
        control_node=control_node,
        agent_nodes=agent_nodes,
        dataset_backend=get_backend_description(options),
        default_volume_size=10,
        certificates=get_certificates(options, control_node, agent_nodes),
        dataset_backend_config_file=agent_config_filepath
    )
    yield returnValue(cluster)


@inlineCallbacks
def run_provisioning(reactor, cluster, actions):
    for action in actions:
        yield perform(make_dispatcher(reactor), action())


@inlineCallbacks
def main(reactor, args, base_path, top_level):
    options = RunOptions()
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

    # todo, need to use the identity file supplied on the command line
    control_node, agent_nodes = get_nodes(options)
    agent_config_filepath = FilePath(options['agent-config'])
    if not agent_config_filepath.isfile():
        print "could not find agent-config at {}".format(
            agent_config_filepath.realpath())
        sys.exit(1)
    cluster = yield create_cluster(
        reactor=reactor,
        options=options,
        control_node_address=options['control-node'],
        agent_node_addresses=agent_nodes,
        agent_config_filepath=agent_config_filepath
    )

    actions = []
    if options['install-flocker']:
        actions.append(partial(install_flocker, cluster))
    if options['install-flocker-docker-plugin']:
        actions.append(partial(install_flocker_docker_plugin, cluster))
    if not options['no-certs']:
        actions.append(partial(distribute_certs, cluster, options))
    actions.append(partial(distribute_agent_yaml, cluster))
    print_install_plan(cluster, options)
    if not options['force']:
        prompt_user_for_continue()
    yield run_provisioning(reactor, cluster, actions)

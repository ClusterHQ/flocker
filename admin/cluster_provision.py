# Todo:
# user has to add their ssh key to the ssh agent, not ideal

import sys
from functools import partial
import yaml

from zope.interface import implementer
from pyrsistent import PClass, field
from twisted.python.usage import Options
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.defer import Deferred
from twisted.python.filepath import FilePath

from effect import parallel
from txeffect import perform

from flocker.provision._install import (
    task_install_flocker,
    run_on_nodes,
    _remove_dataset_fields,
    task_install_control_certificates,
    task_install_node_certificates,
    task_install_api_certificates,
    UnsupportedDistribution,
    task_enable_flocker_control,
    task_enable_flocker_agent,
    task_enable_docker_plugin,
    task_install_docker_plugin,
)
from flocker.provision._ssh import (
    run, run_remotely, sudo_put
)
from flocker.node import DeployerType, BackendDescription
from flocker.provision._ssh._conch import make_dispatcher
from flocker.provision._effect import sequence
from flocker.provision._ca import Certificates
from flocker.common.script import (
    flocker_standard_options,
    ICommandLineScript,
    FlockerScriptRunner
)
from flocker.provision._common import INode


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


@flocker_standard_options
class FlockerProvisionOptions(Options):
    description = "Provision a Flocker cluster."

    optParameters = [
        ['user', None, 'ubuntu', ""],
        ['identity', None, None, ""],
        ['agent-config', None, '', ""],
        ['control-node', None, '', ""],
        ['agent-nodes', None, '', ""],
        ['cluster-name', None, u'flocker_cluster', ""], # optional
        ['cluster-id', None, None, ""], # optional
        ['cluster-file', None, None, ""], # optional
        ['cert-directory', None, None,
         "Directory for storing the cluster certificates. "
         "If not specified, then a temporary directory is used."],
        ['api-cert-name', None, 'plugin', ""],
    ]

    optFlags = [
        ['install-flocker', None, ""],
        ['install-flocker-docker-plugin', None, ""],
        ['no-certs', None, ""],
        ['force', None, ""],
    ]

def get_node_addresses(options):
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


def install_flocker(all_nodes):
    return run_on_nodes(
        all_nodes,
        task=lambda node: task_install_flocker(
            distribution=node.distribution,
        )
    )


def install_flocker_docker_plugin(all_nodes):
    return run_on_nodes(
        all_nodes,
        task=lambda node: task_install_docker_plugin(
            distribution=node.distribution,
        )
    )


def distribute_certs(control_node, agent_nodes, certificates):
    control_command = run_on_nodes(
        [control_node],
        task=lambda node: task_install_control_certificates(
            certificates.cluster.certificate,
            certificates.control.certificate,
            certificates.control.key)
    )

    node_commands = []
    for certnkey, plugin_certnkey, node in zip(certificates.nodes,
                                               certificates.plugins,
                                               agent_nodes):
        cmd = run_remotely(
            username=node.get_default_username(),
            address=node.address,
            commands=sequence([
                task_install_node_certificates(
                    certificates.cluster.certificate,
                    certnkey.certificate,
                    certnkey.key),
                task_install_api_certificates(
                    plugin_certnkey.certificate,
                    plugin_certnkey.key,
                    'plugin')
            ])
        )
        node_commands.append(cmd)
        parallel_node_commands = parallel(node_commands)
    return sequence([control_command, parallel_node_commands])


def distribute_agent_yaml(agent_nodes, agent_config_filepath):
    content = agent_config_filepath.getContent()
    put_config_file = sudo_put(
        path='/etc/flocker/agent.yml',
        content=content,
        log_content_filter=_remove_dataset_fields
    )
    return run_on_nodes(
        nodes=agent_nodes,
        task=lambda node: put_config_file
    )


def post_install_actions(control_node, agent_nodes, options):
    # TODO: should we also open ports on firewall (if enabled)?
    commands = []
    if options['install-flocker']:
        commands.append(
            run_on_nodes(
                nodes=[control_node],
                task=lambda node: task_enable_flocker_control(
                    node.distribution, action='restart')
            )
        )
        commands.append(
            run_on_nodes(
                agent_nodes,
                lambda node: task_enable_flocker_agent(node.distribution,
                                                       action='restart')
            )
        )
    if options['install-flocker-docker-plugin']:
        commands.append(
            run_on_nodes(
                agent_nodes,
                lambda node: task_enable_docker_plugin(node.distribution)
            )
        )

    return sequence(commands)


def print_install_plan(options, control_node, agent_nodes):
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
        directory = get_cert_directory(options)
        user_message.append(
            "New certificates will be distributed to the nodes.")
        user_message.append(
            "Certificates will be created in {}.".format(directory.path))
    user_message.append("Control Node:")
    user_message.append("  - {} ({})".format(
        str(control_node.address), control_node.distribution))
    user_message.append("Agent Nodes:")
    for node in agent_nodes:
        user_message.append("  - {} ({})".format(
            str(node.address), node.distribution))
    print("")
    for line in user_message:
        print(line)
    print


def prompt_user_for_continue():
    answer = raw_input("Do you want to continue? [Y/n]")
    if not answer.lower() == 'y':
        print("Abort.")
        sys.exit(1)


def bail_if_docker_not_installed(agent_nodes):
    def die():
        print "Docker must be installed on all agent nodes"
        sys.exit(1)

    # Todo: implement me
    pass


def get_node_distro(reactor, host, username, d):
    """
    Determines the node's distribution in a series of steps We've made
    some assumptions about the contents of /etc/os-release and that
    might be a bit dangerous.
    """
    def is_os_version(os_string, on_success, on_error):
        perform(
            make_dispatcher(reactor),
            run_remotely(
                username=username,
                address=host,
                commands=sequence([
                    run("grep '{}' /etc/os-release".format(os_string)).on(
                        success=on_success,
                        error=on_error,
                    )
                ])
            )
        )

    def raise_(ex):
        raise ex()

    # TODO: add RHEL support

    def is_centos_7():
        is_os_version('CentOS Linux 7',
                      on_success=lambda v: d.callback('centos-7'),
                      on_error=lambda v: raise_(UnsupportedDistribution))

    def is_ubuntu_15():
        is_os_version('Ubuntu 15.04',
                      on_success=lambda v: d.callback('ubuntu-15.04'),
                      on_error=lambda v: is_centos_7())

    def is_ubuntu_14():
        is_os_version('Ubuntu 14.04',
                      on_success=lambda v: d.callback('ubuntu-14.04'),
                      on_error=lambda v: is_ubuntu_15())

    is_ubuntu_14()


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


def get_cert_directory(options):
    if options['cert-directory']:
        directory = FilePath(options['cert-directory'])
    else:
        directory = FilePath('./{}_certs'.format(options['cluster-name']))
    return directory


def create_cert_directory(options):
    directory = get_cert_directory(options)
    check_cert_directory(directory)
    if not directory.exists():
        directory.makedirs()
    return directory


def check_cert_directory(directory):
    if directory.exists() and not directory.isdir():
        print("Error: Certificate directory {} exists "
              "but is not a directory".format(directory.realpath()))
        sys.exit(1)


def get_doomed_certs(directory):
    check_cert_directory(directory)
    cert_files = ('cluster.crt', 'cluster.key',
                  'node-*.crt', 'node-*.key',
                  'control-*.crt', 'control-*.key',
                  'plugin-*.crt', 'plugin-*.key',
                  'user.crt', 'user.key')
    doomed_certs = []
    for cert_file in cert_files:
        matches = directory.globChildren(cert_file)
        doomed_certs.extend(matches)
    return doomed_certs


def warn_if_overwriting_certs(options):
    directory = get_cert_directory(options)
    doomed_certs = get_doomed_certs(directory)
    if doomed_certs:
        print
        print("Warning you will overwrite the following "
              "files in {}:".format(directory.path))
        for cert_file in doomed_certs:
            print " -{}".format(cert_file.basename())


def delete_doomed_certs(options):
    directory = get_cert_directory(options)
    doomed_certs = get_doomed_certs(directory)
    for path in doomed_certs:
        path.remove()


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
def create_nodes(reactor, options,
                 control_node_address, agent_node_addresses):
    print "inspecting nodes..."
    username = options['user']
    control_deferred = create_node(reactor, control_node_address, username)
    agent_deferreds = []
    for node_address in agent_node_addresses:
        d = create_node(reactor, node_address, username)
        agent_deferreds.append(d)

    # we've fired off all our calls in parallel, now collect them
    agent_nodes = []
    control_node = yield control_deferred
    for node_deferred in agent_deferreds:
        node = yield node_deferred
        agent_nodes.append(node)
    agent_node_addresses = set((a.address for a in agent_nodes))

    if control_node_address in agent_node_addresses:
        all_nodes = agent_nodes
    else:
        all_nodes = [control_node] + agent_nodes
    yield returnValue((control_node, agent_nodes, all_nodes))


@inlineCallbacks
def run_provisioning(reactor, actions):
    for action in actions:
        yield perform(make_dispatcher(reactor), action())


@implementer(ICommandLineScript)
class FlockerProvisionScript(object):
    """
    Command-line script for ``flocker-provision``.
    """

    @inlineCallbacks
    def main(self, reactor, options):
        control_node_address, agent_node_addresses = get_node_addresses(
            options)
        agent_config_filepath = FilePath(options['agent-config'])
        if not agent_config_filepath.isfile():
            print "could not find agent-config at {}".format(
                agent_config_filepath.realpath())
            sys.exit(1)
        control_node, agent_nodes, all_nodes = yield create_nodes(
            reactor, options, control_node_address, agent_node_addresses)

        bail_if_docker_not_installed(agent_nodes)
        warn_if_overwriting_certs(options)
        print_install_plan(options, control_node, agent_nodes)
        if not options['force']:
            prompt_user_for_continue()

        create_cert_directory(options)
        delete_doomed_certs(options)

        certificates = None
        if not options['no-certs']:
            certificates = get_certificates(options, control_node, agent_nodes)

        actions = []
        if options['install-flocker']:
            actions.append(partial(install_flocker, all_nodes))
        if options['install-flocker-docker-plugin']:
            actions.append(partial(install_flocker_docker_plugin, all_nodes))
        if not options['no-certs']:
            actions.append(partial(
                distribute_certs, control_node, agent_nodes, certificates))
        actions.append(partial(
            distribute_agent_yaml, agent_nodes, agent_config_filepath))
        actions.append(partial(
            post_install_actions, control_node, agent_nodes, options))

        yield run_provisioning(reactor, actions)


def flocker_provision_main(reactor, args, base_path, top_level):
    return FlockerScriptRunner(
        FlockerProvisionScript(),
        FlockerProvisionOptions(),
        logging=False).main()

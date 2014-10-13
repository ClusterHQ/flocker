# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from json import loads
from pipes import quote as shellQuote
from subprocess import Popen, PIPE

from flocker.node._docker import Unit

__all__ = [
    # TODO Make things not here private
    'running_units', 'remove_all_containers',
    ]


def running_units(ip):
    """
    Containers which are running on a node.

    This is a hack and could hopefully use docker py over ssh.
    """
    containers = []
    for container in running_container_ids(ip):
        inspect = runSSH(22, 'root', ip, [b"docker"] + [b"inspect"] +
                         [container], None)
        details = loads(inspect)[0]

        # TODO use frozenset of PortMap instances from ``details`` for ports
        # and check the activation state.

        unit = Unit(name=details.get('Name')[1:],
                    container_name=details.get('Name')[1:],
                    activation_state=u'active',
                    container_image=details.get('Config').get('Image'),
                    ports=(),
                    )
        containers.append(unit)

    return containers


def running_container_ids(ip):
    """
    Get the IDs of all containers running on a node.
    """
    ps = runSSH(22, 'root', ip, [b"docker"] + [b"ps"] + [b"-a"] + [b"-q"],
                None)
    return ps.splitlines()


def remove_all_containers(ip):
    """
    Remove all containers on a node
    """
    for container in running_container_ids(ip):
        runSSH(22, 'root', ip, [b"docker"] + [b"rm"] + [b"-f"] + [container],
               None)
        # TODO wait until container is removed before continuing


def runSSH(port, user, node, command, input, key=None):
    """
    # TODO Format this with a PEP8 style

    Run a command via SSH.

    @param port: Port to connect to.
    @type port: L{int}
    @param node: Node to run command on
    @param node: L{bytes}
    @param command: command to run
    @type command: L{list} of L{bytes}
    @param input: Input to send to command.
    @type input: L{bytes}

    @param key: If not L{None}, the path to a private key to use.
    @type key: L{FilePath}

    @return: stdout
    @rtype: L{bytes}
    """
    quotedCommand = ' '.join(map(shellQuote, command))
    command = [
        b'ssh',
        b'-p', b'%d' % (port,),
        ]
    if key is not None:
        command.extend([
            b"-i",
            key.path])
    command.extend([
        b'@'.join([user, node]),
        quotedCommand
    ])
    process = Popen(command, stdout=PIPE, stdin=PIPE)

    result = process.communicate(input)
    if process.returncode != 0:
        raise Exception('Command Failed', command, process.returncode)

    return result[0]

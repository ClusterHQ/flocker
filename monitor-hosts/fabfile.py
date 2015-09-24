from fabric.api import sudo, task, env, put
from pipes import quote as shell_quote
from twisted.python.util import sibpath

# We assume we are running on a fedora 22 AWS image.
# These are setup with an `fedora` user, so hard code that.
env.user = 'fedora'


def cmd(*args):
    """
    Quote the supplied ``list`` of ``args`` and return a command line
    string.

    :param list args: The componants of the command line.
    :return: The quoted command line string.
    """
    return ' '.join(map(shell_quote, args))


def container_exists(name):
    return sudo(cmd('docker', 'inspect',
                    '-f', 'test', name), quiet=True).succeeded


def remove_container(name):
    if container_exists(name):
        sudo(cmd('docker', 'stop', name))
        sudo(cmd('docker', 'rm', '-f', name))


@task
def bootstrap():
    """
    Install docker, and setup data volume.
    """
    sudo('dnf update -y')
    sudo('dnf install -y docker')
    sudo('systemctl enable docker')
    sudo('systemctl start docker')


@task
def start_prometheus():
    PROMETHEUS_IMAGE = 'prom/prometheus:0.15.1'
    remove_container('prometheus')
    if not container_exists('prometheus-data'):
        sudo(cmd(
            'docker', 'run',
            '--name', 'prometheus-data',
            '--entrypoint', '/bin/true',
            PROMETHEUS_IMAGE))
    sudo(cmd('mkdir', '-p', '/srv/prometheus'))
    put(sibpath(__file__, 'prometheus.yml'),
        '/srv/prometheus/prometheus.yml',
        use_sudo=True)
    sudo(cmd('chcon', '-t', 'svirt_sandbox_file_t',
             '/srv/prometheus/prometheus.yml'))
    sudo(cmd(
        'docker', 'run', '-d',
        '--name', 'prometheus',
        '-p', '9090:9090',
        '--net', 'host',
        '-v', ':'.join(['/srv/prometheus/prometheus.yml',
                        '/etc/prometheus/prometheus.yml',
                        'ro']),
        '--volumes-from', 'prometheus-data',
        PROMETHEUS_IMAGE,
        # Store metrics for two months
        '-storage.local.retention=720h0m0s',
        # Options from `CMD`.
        '-config.file=/etc/prometheus/prometheus.yml',
        "-storage.local.path=/prometheus",
        "-web.console.libraries=/etc/prometheus/console_libraries",
        "-web.console.templates=/etc/prometheus/consoles",
    ))


@task
def start_collectd_exporter():
    IMAGE = 'prom/collectd-exporter'  # noqa
    remove_container('collectd_exporter')
    sudo(cmd(
        'docker', 'run', '-d',
        '--name', 'collectd_exporter',
        '-p', '25826:25826/udp',
        '-p', '9103:9103',
        '--net', 'host',
        IMAGE,
        '-collectd.listen-address=0.0.0.0:25826'
    ))

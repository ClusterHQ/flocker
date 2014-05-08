# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Basic fabfile for configuring a buildslave for building flocker.

To install a buildslave on a host, do::

  fab -H $SUDO_USER@$HOSTNAME installBuildslave:$SLAVE_PASSWORD

Then add flocker-buildslave-1.pub as a ssh-key to the appropriate github user.
"""

from fabric.api import task, sudo, put, env, get
from pipes import quote as shellQuote
from twisted.python.util import sibpath

env.always_use_pty = False

def installPackages(packages):
    """
    Install a list of packages.

    @param packages: Packages to install.
    @type packages: L{list} of L{bytes}
    """
    packages = map(shellQuote, packages)
    command = [b'apt-get', b'--yes', b'--quiet', b'install'] + packages
    sudo(b' '.join(command))

@task
def bootstrap():
    """
    Install base packages necesary for buildbot and flocker.
    """
    sudo('apt-get --quiet update')
    installPackages([b'python2.7', b'python2.7-dev', b'python-virtualenv', b'git'])
    installPackages([b'dh-virtualenv', b'debhelper'])

    # SSH Known hosts (particularly github)
    put(sibpath(__file__, 'known_hosts'), '/etc/ssh/ssh_known_hosts', use_sudo=True, mode=0o644)


@task
def installBuildslave(password):
    """
    Install buildslave.
    """
    bootstrap()
    sudo('useradd --base-dir /srv --user-group --create-home --system --shell /bin/bash buildslave')
    sudo('mkdir /srv/buildslave/.ssh', user='buildslave')
    sudo('virtualenv /srv/buildslave/venv', user='buildslave')
    sudo('/srv/buildslave/venv/bin/pip install buildbot-slave',
         user='buildslave')
    sudo('/srv/buildslave/venv/bin/buildslave create-slave /srv/buildslave/slave build.hybridcluster.net flocker-buildslave-1 %s' % (shellQuote(password),),
         user='buildslave')
    sudo("ssh-keygen -t ecdsa -b 521 -N '' -f /srv/buildslave/.ssh/id_ecdsa", user='buildslave')
    get("/srv/buildslave/.ssh/id_ecdsa.pub", 'flocker-buildslave-1.pub')
    put(sibpath(__file__, 'slave.conf'), '/etc/init/slave.conf', use_sudo=True)
    sudo('start slave')

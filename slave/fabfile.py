from fabric.api import task, sudo, put, env
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


@task
def installBuildslave(password):
    """
    Install buildslave.
    """
    bootstrap()
    sudo('useradd --base-dir /srv --user-group --create-home --system --shell /bin/bash buildslave')
    sudo('virtualenv /srv/buildslave/venv', user='buildslave')
    sudo('/srv/buildslave/venv/bin/pip install buildbot-slave')
    sudo('/srv/buildslave/venv/bin/buildslave create-slave /srv/buildslave/slave build.hybridcluster.net flocker-buildslave-1 %s' % (shellQuote(password),))
    put(sibpath(__file__, 'slave.conf'), '/etc/init/slave.conf', use_sudo=True)
    sudo('start slave')

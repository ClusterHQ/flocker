# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Setup for acceptance testing.

Invoke as "python -m acceptance.setup"
"""
if __name__ == "__main__":
    from acceptance.setup import setup_docker_containers
    setup_docker_containers()

def setup_docker_containers():
    """
    Set up docker containers for acceptance testing.

    These are identifiable as the acceptance testing containers so that they
    can later be removed without affecting other Docker containers.

    This is an alternative to
    http://doc-dev.clusterhq.com/gettingstarted/tutorial/vagrant-setup.html#creating-vagrant-vms-needed-for-flocker
    """

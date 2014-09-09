# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Acceptance tests for flocker-cli.
"""

from twisted.trial.unittest import TestCase

def is_fedora(version=20):
    """
    Skip if os is not Fedora of given version.
    """

def is_debian():
    """
    Skip if os is not Debian based
    """

def assert_url_exists(test_case, url):
    """
    Test that a supplied URL (including fragment) is valid.
    """

class InstallFlockerCliLinuxTests(TestCase):
    """
    Tests for the tutorial description of installing flocker-deploy.
    """

    url = "http://docs.clusterhq.com/en/0.1.0/gettingstarted/installation.html#linux"
    
    def setUpClass(cls):
        """
        Print out the link to the corresponding documentation (maybe even print
        it to screen).

        Check for a platform parameter (perhaps and environment variable) and
        create a docker container of that linux version.

        The remainder of the tests in this class will then be run in sequence in
        that container.

        XXX: I think trial allows tests to be run in the order they're defined.

        XXX: Is setUpClass a really bad way to do this?

        XXX: Would also need to tear down the test environment, but for analysis
        of failures it would be essential to be able to attach to the test's
        docker container.
        
        XXX: Perhaps a vagrant VM would be a better environment to run these
        tests?

        XXX: Not sure how these tests could be easily automated for OSX? 
        """

    @is_debian
    def test_install_dependencies_debian(self):
        """
        Installation dependencies can be installed as documented
        """
        # sudo apt-get install gcc python2.7 python-virtualenv python2.7-dev

    @is_fedora
    def test_install_dependencies_fedora(self):
        """
        Installation dependencies can be installed as documented

        """
        # sudo yum install @buildsys-build python python-devel python-virtualenv

    def test_linux_install_download(self):
        """
        The linux-install.sh script can be downloaded.
        """
        # Verify that the documentation contains the correct linux-install.sh
        # script link and download it inside the container.

    def test_linux_install_run(self):
        """
        The linux-install.sh script runs without stderr and with a 0 exit
        status.
        """
        # Run the downloaded script

    def test_flocker_deploy_version(self):
        """
        After installation, the ``flocker-deploy --version`` command runs
        without error and prints the expected output.
        """
        # Run `flocker-deploy` inside the container and check its output.


class InstallMongoDbTests(TestCase):
    """
    Test that mongo client can be installed (as documented) on all platforms.
    """
    url = "http://docs.clusterhq.com/en/0.1.0/gettingstarted/tutorial/vagrant-setup.html#installing-mongodb"

    # TODO


class CreateVagrantNodesTests(TestCase):
    """
    Test that vagrant environment can be created on all supported platforms.
    """
    url = "http://docs.clusterhq.com/en/0.1.0/gettingstarted/tutorial/vagrant-setup.html#creating-vagrant-vms-needed-for-flocker"

    def setUpClass(cls):
        """
        Test that vagrant is installed and fail if not.
        
        Create a docker container in which to run ssh-agent.
        """

    def test_vagrantfile_download(self):
        """
        The Vagrantfile can be downloaded from the documentation.
        """
        # Download http://docs.clusterhq.com/en/0.1.0/_downloads/Vagrantfile

    def test_vagrantfile_run(self):
        """
        The Vagrantfile can be run
        """
        # vagrant up
        # vagrant status

    def test_ssh_add(self):
        """
        The insecure key can be added to ssh-agent.
        """
        # ssh-add ~/.vagrant.d/insecure_private_key
        

class MovingApplicationsTests(TestCase):
    """
    Tests for the Moving Applications section of the tutorial.
    """
    # TODO

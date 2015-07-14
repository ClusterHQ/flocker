.. _installflocker:

==================
Installing Flocker
==================

.. XXX We will improve this introduction with an image. See FLOC-2077

The Flocker CLI is installed on your local machine and provides command line tools to control the cluster. 
This also includes the ``flocker-ca`` tool, which you use to generate certificates for all the Flocker components.

The Flocker agents are installed on any number of nodes in the cluster where your containers will run.
The agent software is included in the ``clusterhq-flocker-node`` package.

There is also a Flocker control service which you must install on one of the agent hosts, or on a separate machine. 
The control service is also included in the ``clusterhq-flocker-node`` package, but is activated separately later in these installation instructions.

.. note:: The agents and control service are pre-installed by the :ref:`Vagrant configuration in the tutorial <tutvagrant>`.

.. note:: If you're interested in developing Flocker (as opposed to simply using it) see :ref:`contribute`.

This document will describe how to install the CLI locally and install the agents and control service on cloud infrastructure.
It also describes how to get Vagrant nodes started which already have these services running.

.. contents::
   :local:
   :backlinks: none
   :depth: 2

.. _installing-flocker-cli:

Installing ``flocker-cli``
==========================

.. _installing-flocker-cli-ubuntu-15.04:

Ubuntu 15.04
------------

On Ubuntu 15.04, the Flocker CLI can be installed from the ClusterHQ repository:

.. task:: install_cli ubuntu-15.04
   :prompt: alice@mercury:~$

.. _installing-flocker-cli-ubuntu-14.04:

Ubuntu 14.04
------------

On Ubuntu 14.04, the Flocker CLI can be installed from the ClusterHQ repository:

.. task:: install_cli ubuntu-14.04
   :prompt: alice@mercury:~$

Other Linux Distributions
-------------------------

.. warning::

   These are guidelines for installing Flocker on a Linux distribution which we do not provide native packages for.
   These guidelines may require some tweaks, depending on the details of the Linux distribution in use.

Before you install ``flocker-cli`` you will need a compiler, Python 2.7, and the ``virtualenv`` Python utility installed.

To install these with the ``yum`` package manager, run:

.. prompt:: bash alice@mercury:~$

   sudo yum install gcc python python-devel python-virtualenv libffi-devel openssl-devel

To install these with ``apt``, run:

.. prompt:: bash alice@mercury:~$

   sudo apt-get update
   sudo apt-get install gcc libssl-dev libffi-dev python2.7 python-virtualenv python2.7-dev

Then run the following script to install ``flocker-cli``:

:version-download:`linux-install.sh.template`

.. version-literalinclude:: linux-install.sh.template
   :language: sh

Save the script to a file and then run it:

.. prompt:: bash alice@mercury:~$

   sh linux-install.sh

The ``flocker-deploy`` command line program will now be available in :file:`flocker-tutorial/bin/`:

.. version-code-block:: console

   alice@mercury:~$ cd flocker-tutorial
   alice@mercury:~/flocker-tutorial$ bin/flocker-deploy --version
   |latest-installable|
   alice@mercury:~/flocker-tutorial$

If you want to omit the prefix path you can add the appropriate directory to your ``$PATH``.
You'll need to do this every time you start a new shell.

.. version-code-block:: console

   alice@mercury:~/flocker-tutorial$ export PATH="${PATH:+${PATH}:}${PWD}/bin"
   alice@mercury:~/flocker-tutorial$ flocker-deploy --version
   |latest-installable|
   alice@mercury:~/flocker-tutorial$

OS X
----

Install the `Homebrew`_ package manager.

Make sure Homebrew has no issues:

.. prompt:: bash alice@mercury:~$

   brew doctor

Fix anything which ``brew doctor`` recommends that you fix by following the instructions it outputs.

Add the ``ClusterHQ/tap`` tap to Homebrew and install ``flocker``:

.. task:: test_homebrew flocker-|latest-installable|
   :prompt: alice@mercury:~$

You can see the Homebrew recipe in the `homebrew-tap`_ repository.

The ``flocker-deploy`` command line program will now be available:

.. version-code-block:: console

   alice@mercury:~$ flocker-deploy --version
   |latest-installable|
   alice@mercury:~$

.. _Homebrew: http://brew.sh
.. _homebrew-tap: https://github.com/ClusterHQ/homebrew-tap

.. _installing-flocker-node:

Installing ``clusterhq-flocker-node``
=====================================

There are a number of ways to install Flocker.

These easiest way to get Flocker going is to use our Vagrant configuration.

- :ref:`Vagrant <vagrant-install>`

It is also possible to deploy Flocker in the cloud, on a number of different providers.

- :ref:`Using Amazon Web Services <aws-install>`
- :ref:`Using Rackspace <rackspace-install>`

It is also possible to install Flocker on any CentOS 7 or Ubuntu 14.04 machine.

- :ref:`Installing on CentOS 7 <centos-7-install>`
- :ref:`Installing on Ubuntu 14.04 <ubuntu-14.04-install>`


.. _vagrant-install:

Vagrant
-------

The easiest way to get Flocker going on a cluster is to run it on local virtual machines using the :ref:`Vagrant configuration in the tutorial <tutvagrant>`.
You can therefore skip this section unless you want to run Flocker on a cluster you setup yourself.

.. _aws-install:

Using Amazon Web Services
-------------------------

.. note:: If you are not familiar with EC2 you may want to `read more about the terminology and concepts <https://fedoraproject.org/wiki/User:Gholms/EC2_Primer>`_ used in this document.
          You can also refer to `the full documentation for interacting with EC2 from Amazon Web Services <http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/EC2_GetStarted.html>`_.


.. The AMI links were created using the ami_links tool in ClusterHQ's internal-tools repository.

#. Choose a nearby region and use the link to it below to access the EC2 Launch Wizard.
   These launch instances using CentOS 7 AMIs (in particular "CentOS 7 x86_64 (2014_09_29) EBS HVM") but it is possible to use any operating system supported by Flocker with AWS.

   * `EU (Frankfurt) <https://console.aws.amazon.com/ec2/v2/home?region=eu-central-1#LaunchInstanceWizard:ami=ami-7cc4f661>`_
   * `South America (Sao Paulo) <https://console.aws.amazon.com/ec2/v2/home?region=sa-east-1#LaunchInstanceWizard:ami=ami-bf9520a2>`_
   * `Asia Pacific (Tokyo) <https://console.aws.amazon.com/ec2/v2/home?region=ap-northeast-1#LaunchInstanceWizard:ami=ami-89634988>`_
   * `EU (Ireland) <https://console.aws.amazon.com/ec2/v2/home?region=eu-west-1#LaunchInstanceWizard:ami=ami-e4ff5c93>`_
   * `US East (Northern Virginia) <https://console.aws.amazon.com/ec2/v2/home?region=us-east-1#LaunchInstanceWizard:ami=ami-96a818fe>`_
   * `US East (Northern California) <https://console.aws.amazon.com/ec2/v2/home?region=us-west-1#LaunchInstanceWizard:ami=ami-6bcfc42e>`_
   * `US West (Oregon) <https://console.aws.amazon.com/ec2/v2/home?region=us-west-2#LaunchInstanceWizard:ami=ami-c7d092f7>`_
   * `Asia Pacific (Sydney) <https://console.aws.amazon.com/ec2/v2/home?region=ap-southeast-2#LaunchInstanceWizard:ami=ami-bd523087>`_
   * `Asia Pacific (Singapore) <https://console.aws.amazon.com/ec2/v2/home?region=ap-southeast-1#LaunchInstanceWizard:ami=ami-aea582fc>`_

#. Configure the instance.
   Complete the configuration wizard; in general the default configuration should suffice.   

   * Choose instance type. We recommend at least the ``m3.large`` instance size.
   * Configure instance details. You will need to configure a minimum of 2 instances.
   * Add storage. It is important to note that the default storage of an AWS image can be too small to store popular Docker images, so we recommend choosing at least 16GB to avoid potential disk space problems.
   * Tag instance.
   * Configure security group.
      
     * If you wish to customize the instance's security settings, make sure to permit SSH access from the administrators machine (for example, your laptop).
     * To enable Flocker agents to communicate with the control service and for external access to the API, add a custom TCP security rule enabling access to ports 4523-4524.
     * Keep in mind that (quite reasonably) the default security settings firewall off all ports other than SSH.
     * For example, if you run the MongoDB tutorial you won't be able to access MongoDB over the Internet, nor will other nodes in the cluster.
     * You can choose to expose these ports but keep in mind the consequences of exposing unsecured services to the Internet.
     * Links between nodes will also use public ports but you can configure the AWS VPC to allow network connections between nodes and disallow them from the Internet.

   * Review to ensure your instances have sufficient storage and your security groups have the required ports.

   Launch when you are ready to proceed.

#. Add the *Key* to your local key chain (download it from the AWS web interface first if necessary):

   .. prompt:: bash alice@mercury:~$

      mv ~/Downloads/my-instance.pem ~/.ssh/
      chmod 600 ~/.ssh/my-instance.pem
      ssh-add ~/.ssh/my-instance.pem

#. Look up the public DNS name or public IP address of each new instance.
   Log in as user ``centos`` (or the relevant user if you are using another AMI).
   For example:

   .. prompt:: bash alice@mercury:~$

      ssh centos@ec2-AA-BB-CC-DD.eu-west-1.compute.amazonaws.com

#. Allow SSH access for the ``root`` user on each node, then log out.

   .. task:: install_ssh_key
      :prompt: [user@aws]$

#. Log back into the instances as user "root" on each node.
   For example:

   .. prompt:: bash alice@mercury:~$

      ssh root@ec2-AA-BB-CC-DD.eu-west-1.compute.amazonaws.com


#. Follow the operating system specific installation instructions below on each node.


.. _rackspace-install:

Using Rackspace
---------------

Another way to get a Flocker cluster running is to use Rackspace.
You'll probably want to setup at least two nodes.

#. Create a new cloud server:

   * Visit https://mycloud.rackspace.com
   * Click "Create Server".
   * Choose a supported Linux distribution (either CentOS 7 or Ubuntu 14.04) as your image.
   * Choose a Flavor.
     We recommend at least "8 GB General Purpose v1".
   * Add your SSH key

#. SSH in:

   You can find the IP in the Server Details page after it is created.

   .. prompt:: bash alice@mercury:~$

      ssh root@203.0.113.109

#. Follow the installation instructions for your chosen distribution:

   * :ref:`centos-7-install`
   * :ref:`ubuntu-14.04-install`

.. _centos-7-install:

Installing on CentOS 7
----------------------

.. note:: The following commands all need to be run as root on the machine where ``clusterhq-flocker-node`` will be running.

First disable SELinux.

.. task:: disable_selinux centos-7
   :prompt: [root@centos]#

.. note:: Flocker does not currently set the necessary SELinux context types on the filesystem mount points that it creates on nodes.
          This prevents Docker containers from accessing those filesystems as volumes.
          A future version of Flocker may provide a different integration strategy.
          See :issue:`619`.

Now install the ``flocker-node`` package.
To install ``flocker-node`` on CentOS 7 you must install the RPM provided by the ClusterHQ repository.
The following commands will install the two repositories and the ``flocker-node`` package.
Paste them into a root console on the target node:

.. task:: install_flocker centos-7
   :prompt: [root@centos]#

Installing ``flocker-node`` will automatically install Docker, but the ``docker`` service may not have been enabled or started.
To enable and start Docker, run the following commands in a root console:

.. task:: enable_docker centos-7
   :prompt: [root@centos]#

Finally, you will need to run the ``flocker-ca`` tool that is installed as part of the CLI package.
This tool generates TLS certificates that are used to identify and authenticate the components of your cluster when they communicate, which you will need to copy over to your nodes.
Please see the :ref:`cluster authentication <authentication>` instructions.

.. _ubuntu-14.04-install:

Installing on Ubuntu 14.04
--------------------------

.. note:: The following commands all need to be run as root on the machine where ``clusterhq-flocker-node`` will be running.

Setup the pre-requisite repositories and install the ``clusterhq-flocker-node`` package.

.. task:: install_flocker ubuntu-14.04
   :prompt: [root@ubuntu]#

Finally, you will need to run the ``flocker-ca`` tool that is installed as part of the CLI package.
This tool generates TLS certificates that are used to identify and authenticate the components of your cluster when they communicate, which you will need to copy over to your nodes.
Please continue onto the next section, with the cluster authentication instructions.

.. _authentication:

Configuring Cluster Authentication
==================================

Communication between the different parts of your cluster is secured and authenticated via TLS.
The Flocker CLI package includes the ``flocker-ca`` tool that is used to generate TLS certificate and key files that you will need to copy over to your nodes.

#. Once you have installed the ``flocker-node`` package, you will need to generate:

   - A control service certificate and key file, to be copied over to the machine running your :ref:`control service <architecture>`.
   - A certificate and key file for each of your nodes, which you will also need to copy over to the nodes.

#. Both types of certificate will be signed by a certificate authority identifying your cluster, which is also generated using the ``flocker-ca`` tool.

#. Using the machine on which you installed the ``flocker-cli`` package, run the following command to generate your cluster's root certificate authority, replacing ``mycluster`` with any name you like to uniquely identify this cluster.

   .. prompt:: bash 

      flocker-ca initialize mycluster

   .. note:: This command creates :file:`cluster.key` and :file:`cluster.crt`.
             Please keep :file:`cluster.key` secret, as anyone who can access it will be able to control your cluster.

   You will find the files :file:`cluster.key` and :file:`cluster.crt` have been created in your working directory.

#. The file :file:`cluster.key` should be kept only by the cluster administrator; it does not need to be copied anywhere.

   .. warning:: The cluster administrator needs this file to generate new control service, node and API certificates.
                The security of your cluster depends on this file remaining private.
                Do not lose the cluster private key file, or allow a copy to be obtained by any person other than the authorised cluster administrator.

#. You are now able to generate authentication certificates for the control service and each of your nodes.
   To generate the control service certificate, run the following command from the same directory containing your authority certificate generated in the previous step:

   - Replace ``example.org`` with the hostname of your control service node; this hostname should match the hostname you will give to HTTP API clients.
   - It should be a valid DNS name that HTTPS clients can resolve since they will use it as part of TLS validation.
   - Using an IP address is not recommended as it may break some HTTPS clients.

     .. code-block:: console

        $ flocker-ca create-control-certificate example.org

#. At this point you will need to create a :file:`/etc/flocker` directory on each node:

   .. code-block:: console

      root@centos-7:~/$ mkdir /etc/flocker

#. You will need to copy both :file:`control-example.org.crt` and :file:`control-example.org.key` over to the node that is running your control service, to the directory :file:`/etc/flocker` and rename the files to :file:`control-service.crt` and :file:`control-service.key` respectively.
   You should also copy the cluster's public certificate, the :file:`cluster.crt` file.

#. On the server, the :file:`/etc/flocker` directory and private key file should be set to secure permissions via :command:`chmod`:

   .. code-block:: console

      root@centos-7:~/$ chmod 0700 /etc/flocker
      root@centos-7:~/$ chmod 0600 /etc/flocker/control-service.key

   You should copy these files via a secure communication medium such as SSH, SCP or SFTP.

   .. warning:: Only copy the file :file:`cluster.crt` to the control service and node machines, not the :file:`cluster.key` file; this must kept only by the cluster administrator.

#. You will also need to generate authentication certificates for each of your nodes.
   Do this by running the following command as many times as you have nodes; for example, if you have two nodes in your cluster, you will need to run this command twice.

   This step should be followed for all nodes on the cluster, as well as the machine running the control service.
   Run the command in the same directory containing the certificate authority files you generated in the first step.

   .. code-block:: console

      $ flocker-ca create-node-certificate

   This creates :file:`8eab4b8d-c0a2-4ce2-80aa-0709277a9a7a.crt`. Copy it over to :file:`/etc/flocker/node.crt` on your node machine, and make sure to chmod 0600 it.

   The actual certificate and key file names generated in this step will vary from the example above; when you run ``flocker-ca create-node-certificate``, a UUID for a node will be generated to uniquely identify it on the cluster and the files produced are named with that UUID.

#. As with the control service certificate, you should securely copy the generated certificate and key file over to your node, along with the :file:`cluster.crt` certificate.

   - Copy the generated files to :file:`/etc/flocker` on the target node and name them :file:`node.crt` and :file:`node.key`.
   - Perform the same :command:`chmod 600` commands on :file:`node.key` as you did for the control service in the instructions above.
   - The :file:`/etc/flocker` directory should be set to ``chmod 700``.

You should now have :file:`cluster.crt`, :file:`node.crt`, and :file:`node.key` on each of your agent nodes, and :file:`cluster.crt`, :file:`control-service.crt`, and :file:`control-service.key` on your control node.

Before you can use Flocker's API you will also need to :ref:`generate a client certificate <generate-api>`.

You can read more about how Flocker's authentication layer works in the :ref:`security and authentication guide <security>`.

.. _post-installation-configuration:

Post-Installation Configuration
-------------------------------

Your firewall will need to allow access to the ports your applications are exposing.

.. warning::

   Keep in mind the consequences of exposing unsecured services to the Internet.
   Both applications with exposed ports and applications accessed via links will be accessible by anyone on the Internet.

Enabling the Flocker control service 
------------------------------------

On CentOS 7
...........

.. task:: enable_flocker_control centos-7
   :prompt: [root@control-node]#

The control service needs to be accessible remotely.
You will need to configure FirewallD to allow access to the control service HTTP API and for agent connections.
Note that on some environments, in particular AWS, the ``firewalld`` package is not installed and the ``firewall-cmd`` program will not be found.
If that is the case then just skip these commands.
Otherwise run:

.. task:: open_control_firewall centos-7
   :prompt: [root@control-node]#

For more details on configuring the firewall, see the `FirewallD documentation <https://access.redhat.com/documentation/en-US/Red_Hat_Enterprise_Linux/7/html/Security_Guide/sec-Using_Firewalls.html>`_.

On AWS, an external firewall is used instead, which will need to be configured similarly.

On Ubuntu
.........

.. task:: enable_flocker_control ubuntu-14.04
   :prompt: [root@control-node]#

The control service needs to accessible remotely.
To configure ``UFW`` to allow access to the control service HTTP API, and for agent connections:

.. task:: open_control_firewall ubuntu-14.04
   :prompt: [root@control-node]#

For more details on configuring the firewall, see Ubuntu's `UFW documentation <https://help.ubuntu.com/community/UFW>`_.

On AWS, an external firewall is used instead, which will need to be configured similarly.

.. _agent-yml:

Configuring the Flocker agent
-----------------------------

To start the agents on a node, a configuration file must exist on the node at ``/etc/flocker/agent.yml``.
The file must always include ``version`` and ``control-service`` items similar to these:

.. code-block:: yaml

   "version": 1
   "control-service":
      "hostname": "${CONTROL_NODE}"
      "port": 4524

The value of the hostname field should be a hostname or IP that is routable from all your node agents.

When configuring node agents, consider whether the control service location you choose will have multiple possible addresses, and ensure the hostname you provide is the correct one.
You should never choose ``127.0.0.1`` or ``localhost`` as the hostname, even if the control service is on same machine as the node agent.

Please note that the interface you choose will be the one that linked traffic will be routed over.
If you're in environment where some interfaces have bandwidth costs and some are free (for example, AWS), ensure that you choose the private interface where bandwidth costs don't apply.

``${CONTROL_NODE}`` should be replaced with the address of the control node.
The optional ``port`` variable is the port on the control node to connect to.
This value must agree with the configuration for the control service telling it on what port to listen.
Omit the ``port`` from both configurations and the services will automatically agree.

The file must also include a ``dataset`` item.
This selects and configures a dataset backend.
All nodes must be configured to use the same dataset backend.

.. _openstack-dataset-backend:

OpenStack Block Device Backend Configuration
............................................

The OpenStack backend uses Cinder volumes as the storage for datasets.
This backend can be used with Flocker dataset agent nodes run by OpenStack Nova.
The configuration item to use OpenStack should look like:

.. code-block:: yaml

   dataset:
       backend: "openstack"
       region: "<region slug; for example, LON>"
       auth_plugin: "<authentication plugin>"
       ...

Make sure that the ``region`` specified matches the region where the Flocker nodes run.
OpenStack must be able to attach volumes created in that region to your Flocker agent nodes.

.. note::
	For the Flocker OpenStack integration to be able to identify the virtual machines where you run the Flocker agents, and to attach volumes to them, those virtual machines **must be provisioned through OpenStack** (via Nova).

.. XXX FLOC-2091 - Fix up this section.

If the OpenStack cloud uses certificates that are issued by a private Certificate Authority (CA), add the field ``verify_ca_path`` to the dataset stanza, with the path to the CA certificate.

.. code-block:: yaml

   dataset:
       backend: "openstack"
       region: "DFW"
       verify_ca_path: "/etc/flocker/openstack-ca.crt"
       auth_plugin: "password"
       ...

For testing purposes, it is possible to turn off certificate verification, by setting the ``verify_peer`` field to ``false``.

.. warning::

   Only use this insecure setting for troubleshooting, as it is does not check that the remote server's credential is valid.

.. code-block:: yaml

   dataset:
       backend: "openstack"
       region: "DFW"
       verify_peer: false
       auth_plugin: "password"
       ...

Other items are typically required but vary depending on the `OpenStack authentication plugin selected <http://docs.openstack.org/developer/python-keystoneclient/authentication-plugins.html#loading-plugins-by-name>`_
(Flocker relies on these plugins; it does not provide them itself).

Flocker does provide explicit support for a ``rackspace`` authentication plugin.
This plugin requires ``username``, ``api_key``, and ``auth_url``.

For example:

.. code-block:: yaml

   dataset:
       backend: "openstack"
       region: "<region slug; for example, LON>"
       auth_plugin: "rackspace"
       username: "<your rackspace username>"
       api_key: "<your rackspace API key>"
       auth_url: "https://identity.api.rackspacecloud.com/v2.0"

To find the requirements for other plugins, see the appropriate documentation in the OpenStack project or provided with the plugin.

.. _aws-dataset-backend:

Amazon AWS / EBS Block Device Backend Configuration
...................................................

The AWS backend uses EBS volumes as the storage for datasets.
This backend can be used when Flocker dataset agents are run on EC2 instances.
The configuration item to use AWS should look like:

.. code-block:: yaml

   dataset:
       backend: "aws"
       region: "<region slug; for example, us-west-1>"
       zone: "<availability zone slug; for example, us-west-1a>"
       access_key_id: "<AWS API key identifier>"
       secret_access_key: "<Matching AWS API key>"

Make sure that the ``region`` and ``zone`` match each other and that both match the region and zone where the Flocker agent nodes run.
AWS must be able to attach volumes created in that availability zone to your Flocker nodes.

.. _emc-dataset-backend:

EMC Block Device Backend Configuration
......................................

EMC provide plugins for Flocker integration with `ScaleIO`_ and `XtremIO`_.
For more information, including installation, testing and usage instructions, visit the following links to their GitHub repositories:

* `EMC ScaleIO Flocker driver on GitHub`_
* `EMC XtremIO Flocker driver on GitHub`_

.. XXX FLOC 2442 and 2443 to expand this EMC/Backend storage section

.. _zfs-dataset-backend:

ZFS Peer-to-Peer Backend Configuration (Experimental)
.....................................................

The ZFS backend uses node-local storage and ZFS filesystems as the storage for datasets.
The ZFS backend remains under development, it is not expected to operate reliably in many situations, and its use with any data that you cannot afford to lose is **strongly** discouraged at this time.
This backend has no infrastructure requirements: it can run no matter where the Flocker dataset agents run.
The configuration item to use ZFS should look like:

.. code-block:: yaml

   "dataset":
      "backend": "zfs"
      "pool": "flocker"

.. This section could stand to be improved.
   Some of the suggested steps are not straightforward.
   FLOC-2092

The pool name must match a ZFS storage pool that you have created on all of the Flocker agent nodes.
This requires first installing `ZFS on Linux <http://zfsonlinux.org/>`_.
You must also set up SSH keys at ``/etc/flocker/id_rsa_flocker`` which will allow each Flocker dataset agent node to authenticate to all other Flocker dataset agent nodes as root.

.. _loopback-dataset-backend:

Loopback Block Device Backend Configuration (INTERNAL TESTING)
..............................................................

The Loopback backend uses node-local storage as storage for datasets.
It has no data movement functionality.
It serves primarily as a development and testing tool for the other block device backend implementations.
You may find it useful if you plan to work on Flocker itself.
This backend has no infrastructure requirements: it can run no matter where the Flocker dataset agents run.
The configuration item to use Loopback should look like:

.. code-block:: yaml

   "dataset":
      "backend": "loopback"
      "root_path": "/var/lib/flocker/loopback"

The ``root_path`` is a local path on each Flocker dataset agent node where dataset storage will reside.

Enabling the Flocker agent service on CentOS 7
----------------------------------------------

Run the following commands to enable the agent service:

.. task:: enable_flocker_agent centos-7
   :prompt: [root@agent-node]#

Enabling the Flocker agent service on Ubuntu
--------------------------------------------

Run the following commands to enable the agent service:

.. task:: enable_flocker_agent ubuntu-14.04
   :prompt: [root@agent-node]#

What to do next
===============

Optional ZFS Backend Configuration
----------------------------------

If you intend to use a ZFS backend, this requires ZFS to be installed.


Installing ZFS on CentOS 7
..........................

Installing ZFS requires the kernel development headers for the running kernel.
Since CentOS doesn't provide easy access to old package versions,
the easiest way to get appropriate headers is to upgrade the kernel and install the headers.

.. task:: upgrade_kernel centos-7
   :prompt: [root@centos-7]#

You will need to reboot the node after updating the kernel.

.. prompt:: bash [root@centos-7]#

   shutdown -r now

You must also install the ZFS package repository.

.. task:: install_zfs centos-7
   :prompt: [root@centos-7]#


Installing ZFS on Ubuntu 14.04
..............................

.. task:: install_zfs ubuntu-14.04
   :prompt: [root@ubuntu-14.04]#


Creating a ZFS Pool
...................

Flocker requires a ZFS pool.
The pool is typically named ``flocker`` but this is not required.
The following commands will create a 10 gigabyte ZFS pool backed by a file:

.. task:: create_flocker_pool_file
   :prompt: [root@node]#

.. note:: It is also possible to create the pool on a block device.

.. XXX: Document how to create a pool on a block device: https://clusterhq.atlassian.net/browse/FLOC-994

To support moving data with the ZFS backend, every node must be able to establish an SSH connection to all other nodes.
So ensure that the firewall allows access to TCP port 22 on each node from the every node's IP addresses.

Next Step
---------

The next section describes your next step - setting up an :ref:`authenticated user<authenticate>`.

.. _ScaleIO: https://www.emc.com/storage/scaleio/index.htm
.. _XtremIO: https://www.emc.com/storage/xtremio/overview.htm
.. _EMC ScaleIO Flocker driver on GitHub: https://github.com/emccorp/scaleio-flocker-driver
.. _EMC XtremIO Flocker driver on GitHub: https://github.com/emccorp/xtremio-flocker-driver

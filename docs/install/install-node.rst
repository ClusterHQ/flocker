.. _installing-flocker-node:

====================================
Installing the Flocker Node Services
====================================

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
=======

The easiest way to get Flocker going on a cluster is to run it on local virtual machines using the :ref:`Vagrant configuration in the tutorial <tutvagrant>`.
You can therefore skip this section unless you want to run Flocker on a cluster you setup yourself.

.. _aws-install:

Using Amazon Web Services
=========================

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
===============

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
======================

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
==========================

.. note:: The following commands all need to be run as root on the machine where ``clusterhq-flocker-node`` will be running.

Setup the pre-requisite repositories and install the ``clusterhq-flocker-node`` package.

.. task:: install_flocker ubuntu-14.04
   :prompt: [root@ubuntu]#

Finally, you will need to run the ``flocker-ca`` tool that is installed as part of the CLI package.
This tool generates TLS certificates that are used to identify and authenticate the components of your cluster when they communicate, which you will need to copy over to your nodes.
Please continue onto the next section, with the cluster authentication instructions.

Next Step
=========

In the next step :ref:`the node control and agent services will be configured and started.<post-installation-configuration>`.

.. _aws-install:

==========================================
Setting Up Nodes Using Amazon Web Services
==========================================

If you are not familiar with AWS EC2, you may want to `read more about the terminology and concepts <https://fedoraproject.org/wiki/User:Gholms/EC2_Primer>`_ used in this document.
You can also refer to `the full documentation for interacting with EC2 from Amazon Web Services <http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/EC2_GetStarted.html>`_.

.. The AMI links were created using the ami_links tool in ClusterHQ's internal-tools repository.

#. Choose a region, and an Amazon Machine Image (AMI):

   * Launch the `AWS EC2 Launch Wizard <https://eu-west-1.console.aws.amazon.com/ec2/v2/home?region=eu-west-1#LaunchInstanceWizard:>`_.
   * In the header bar, next to your user name, you can change which region you'd like to use. 
     The link provided defaults to EU (Ireland), but change this to another region if you'd prefer.
   * Choose an AMI.
     You can choose any :ref:`operating system supported by Flocker<supported-operating-systems>` with AWS. 

.. note:: 
   If you want to choose a CentOS 7 AMI, you might not find it listed in the provided link. 
   
   Use the links below to launch instances using CentOS 7 AMIs (specifically ``CentOS 7 x86_64 (2014_09_29) EBS HVM``):

   * `EU (Frankfurt) <https://console.aws.amazon.com/ec2/v2/home?region=eu-central-1#LaunchInstanceWizard:ami=ami-7cc4f661>`_
   * `South America (Sao Paulo) <https://console.aws.amazon.com/ec2/v2/home?region=sa-east-1#LaunchInstanceWizard:ami=ami-bf9520a2>`_
   * `Asia Pacific (Tokyo) <https://console.aws.amazon.com/ec2/v2/home?region=ap-northeast-1#LaunchInstanceWizard:ami=ami-89634988>`_
   * `EU (Ireland) <https://console.aws.amazon.com/ec2/v2/home?region=eu-west-1#LaunchInstanceWizard:ami=ami-e4ff5c93>`_
   * `US East (Northern Virginia) <https://console.aws.amazon.com/ec2/v2/home?region=us-east-1#LaunchInstanceWizard:ami=ami-96a818fe>`_
   * `US East (Northern California) <https://console.aws.amazon.com/ec2/v2/home?region=us-west-1#LaunchInstanceWizard:ami=ami-6bcfc42e>`_
   * `US West (Oregon) <https://console.aws.amazon.com/ec2/v2/home?region=us-west-2#LaunchInstanceWizard:ami=ami-c7d092f7>`_
   * `Asia Pacific (Sydney) <https://console.aws.amazon.com/ec2/v2/home?region=ap-southeast-2#LaunchInstanceWizard:ami=ami-bd523087>`_
   * `Asia Pacific (Singapore) <https://console.aws.amazon.com/ec2/v2/home?region=ap-southeast-1#LaunchInstanceWizard:ami=ami-aea582fc>`_

#. Configure the instance:

   Complete each of the steps in the EC2 wizard using the following suggestions (fields not mentioned below can be left with the default configuration):

   * **Choose instance type**:
     We recommend at least the ``m3.large`` instance size.
   * **Configure instance details**:
     You will need to configure a minimum of 2 instances.
   * **Add storage**:
     It is important to note that the default storage of an AWS image can be too small to store popular Docker images, so we recommend choosing at least 16 GB for the root device to avoid potential disk space problems.
   * **Tag instance**:
     Flocker does not require the instance to be tagged.
   * **Configure security group**:
      
     * If you wish to customize the instance's security settings, make sure to permit SSH access from the administrators machine (for example, your laptop).
     * To enable Flocker agents to communicate with the :ref:`Flocker control service <enabling-control-service>` and for external access to the API, add a custom TCP security rule enabling access to ports 4523-4524.
     * Keep in mind that (quite reasonably) the default security settings firewall off all ports other than SSH.
     * You can choose to expose these ports but keep in mind the consequences of exposing unsecured services to the Internet.
     * Links between nodes will also use public ports but you can configure the AWS VPC to allow network connections between nodes and disallow them from the Internet.

   * **Launch**:
     This opens a prompt for you to either select an existing key pair, or create and download a new key pair.

   Click **Launch your instances** when you are happy to proceed.

#. Add the key to your local keychain (download it from the AWS web interface first if necessary):

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


#. Go to the installation instructions specific to your operating system in :ref:`installing-flocker-node`, to install ``clusterhq-flocker-node`` on each node in your cluster:

   * :ref:`centos-7-install`
   * :ref:`ubuntu-14.04-install`

============================================
Maintaining Flocker CloudFormation Installer
============================================

Architecture
------------

The Installer uses AWS CloudFormation to deploy a stack comprising Ubuntu 14.04, Docker 1.9.1, Swarm 1.0.1, Flocker 1.9.0.
The stack is composed of 2 Agent Nodes (m3.large), 1 Control Node (m3.large), and 1 Client Node (m3.medium) instances.

We use `troposphere`_ package to generate the CloudFormation template.

How does CloudFormation work?
-----------------------------

CloudFormation takes an input template composed of resources.
The template is manifested as a stack on AWS.
When the stack is ready, you will see an ``Outputs`` tab in CloudFormation web interface, which is populated with necessary information to connect to and use the stack.

CloudFormation allows setting resource dependencies (e.g. start creating Resource A after Resource B is created).
We use this feature to delay booting the Agent Node(s) and Client Node until the Control Node has booted.

The Control Node hosts the Flocker Control Service and the Swarm Manager.
The Control Node is also responsible for certificate generation for Flocker, Docker, and Swarm.
We use an S3 bucket to broker certificate distribution:
Control Node uploads Flocker certificates and agent.yml to the bucket; Agent Node(s) and Client Node download Flocker configuration from the bucket.
For Docker TLS, the Control Node uploads a Certificate Authority to the bucket.
Agent Node(s) and Client Node create certificates for themselves using the CA downloaded from S3.

Publishing CloudFormation template
----------------------------------

Generate CloudFormation JSON template:

.. prompt:: bash #

   admin/create-cloudformation-template \
       --client-ami-map-body="$(< $PWD/docker.json)" \
       --node-ami-map-body="$(< $PWD/flocker.json)" \
       > /tmp/flocker-cluster.cloudformation.json

Publish template to `InstallerS3Bucket`_ .

.. prompt:: bash #

   s3cmd --access_key=<aws access key> --secret_key=<aws secret key> \
       put --force --acl-public  \
       /tmp/flocker-cluster.cloudformation.json \
       s3://installer.downloads.clusterhq.com/

.. note:: The template will be published as a public URL.


Building CloudFormation Machine Images
--------------------------------------

The Flocker virtual machine images used in the CloudFormation template can be built using a tool called Packer.
The Flocker source repository has an ``admin/packer`` sub-directory which contains Packer templates and provisioning scripts.
These are used to create Ubuntu AMI images for use in the Flocker CloudFormation demonstration environment.
The images are built in two steps: Ubuntu + Docker base image then Flocker the image.
This speeds up the build process because Docker does not have to be installed each time we update the Flocker image.
It also allows control over the version of Docker in our demonstration environment.
i.e we only need to upgrade when a new version of Docker is released and when it is supported by Flocker.

Follow these steps to build the virtual machine images:

1. Install Packer.

   See https://www.packer.io/ for complete installation instructions.

   The Packer command must be installed at ``/opt/packer/packer``.

2. Build the Ubuntu-14.04 + Docker + Docker Swarm base image.

   .. prompt:: bash #

      DOCKER_VERSION=1.10.0 \
      SWARM_VERSION=1.1.0 \
      ./admin/publish-installer-images --copy_to_all_regions --template=docker

   A new AMI image will be built in the ``us-west-1`` region.
   That image will be copied to all available AWS regions.
   The region specific AMI image IDs will be printed to ``stdout`` in JSON format.
   Make a note of the ``us-west-1`` AMI image ID because you'll use it for building the Flocker AMI in the next step.

   .. note::

      .. XXX: This process should be automated and added to the script.
         It may be useful to implement this as a standalone command / library that can be used elsewhere in the Flocker infrastructure.
         E.g. ``admin/latest_cloud_base_image --distribution=ubuntu-14.04 --provider=aws``

      The script above will use a fixed Ubuntu-14.04 base image.
      But the Ubuntu-14.04 base AMI images are updated frequently and it is a good idea to use a recent image.
      The IDs of the latest images can be found at:

      * https://cloud-images.ubuntu.com/locator/ec2/

      Look for an image with the following parameters:

      * Instance type: ``hvm:ebs``.
      * Architecture: ``amd64``.
      * Version: ``14.04 LTS``.
      * Zone: ``us-west-1`` (or which ever region you choose to build the images in)

3. Build the Flocker image.

   This image is based on the ``us-west-1`` image generated in the previous step.
   Substitute the name of the ``us-west-1`` image in the following command line.

   .. prompt:: bash #

      FLOCKER_VERSION=1.10.1 \
      ./admin/publish-installer-images \
          --copy_to_all_regions \
          --template=flocker \
          --source_ami=<name of AMI image from previous step>"

   A new AMI image will be built in the ``us-west-1`` region.
   That image will be copied to all available AWS regions.
   The region specific AMI image IDs will be printed to ``stdout`` in JSON format.

   .. XXX: We need a new option to consume that JSON in line or from a URL.
      E.g. ``--source_ami_map_url <S3 URL>`` and ``--source_ami_map_body <inline JSON>``

4. Add the new images to the CloudFormation template.

   Copy the ``docker`` and ``flocker`` regional AMI IDs into ``cloudformation.py`` and follow the instructions above to create and publish a new template.


How are user-specific inputs (like AWS AccessKeyID) sourced?
------------------------------------------------------------

User's AWS ``AccessKeyID``, ``SecretAccessKey``, and ``KeyPair`` are sourced as `InputParameters`_ in CloudFormation template.

Why is there a wrapper around S3 commands?
------------------------------------------

Under certain circumstances, Agent Node(s) and/or Client Node might boot before the Control Node has published cluster certificates to S3.
Hence, the wait and retry loop around S3 commands to allow Agent Node(s) and Client Node wait for S3 bucket to be populated with data by Control Node.

What happens if CloudFormation fails to bring up the stack?
-----------------------------------------------------------

If any of the resources corresponding to the stack fail to reach ``CREATE_COMPLETE`` state, the stack is automatically rolled back.
As a result, the user gets a functional stack or no stack.

How are Flocker, Docker, and Swarm configured?
----------------------------------------------

Once the `AWS::EC2::Instance`_ for the Agent/Control Node boots up, CloudFormation allows you to run user defined scripts.
These scripts are part of `UserData`_ section of cloud-init.
We plugin scripts for configuring Flocker, Docker, and Swarm into `UserData`_.

What happens if Flocker, Docker, or Swarm configuration fails?
--------------------------------------------------------------

We use an `AWS::CloudFormation::WaitCondition`_ resource and a corresponding `AWS::CloudFormation::WaitConditionHandle`_ to wait for `UserData`_ configuration to complete.
At the end of `UserData`_ script, we signal the WaitConditionHandle corresponding to the instance.
This transitions the WaitCondition resource from ``CREATE_IN_PROGRESS`` to ``CREATE_COMPLETE`` state.
The stack resource (`AWS::CloudFormation::Stack`_) is now unblocked to transition to ``CREATE_COMPLETE`` state.

If the `UserData`_ configuration fails, or takes longer than 600 seconds, the WaitCondition resource transitions to `CREATE_FAILED` state, triggering a rollback of the stack.

How do I debug a failed stack creation?
---------------------------------------

By default, failure to bring up any of stack components rolls back the stack.
Since the primary audience of the stack is potential customers, we want to give them a fully functional stack or no stack.

If you want to test new additions to the installer, and want to preserve stack state upon failure, please set the `RollbackOnFailure`_ option to ``No`` during stack creation time.

One of my stack nodes failed to bring up Flocker/Docker/Swarm. How do I debug?
------------------------------------------------------------------------------

On the corresponding EC2 instance, please look at ``/var/log/cloud-init-output.log`` to triage which stage of `UserData`_ failed.
Contents of ``/var/log/cloud-init-output.log`` are also available via `SystemLog`_ on the instance.

The `UserData`_ script for this instance is located at ``/var/lib/cloud/instance/user-data.txt``.
This can be handy to reproduce a bug, and while prototyping enhancements to the installer.
For example, if you would like to add Kubernetes as the scheduler, edit ``/var/lib/cloud/instance/user-data.txt`` to add Kubernetes setup, test on the EC2 instance, then add the working bash script to ``cloudformation.py``.

.. _UserData: http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-metadata.html#instancedata-add-user-data
.. _AWS::EC2::Instance: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-ec2-instance.html
.. _AWS::CloudFormation::WaitCondition: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-waitcondition.html
.. _AWS::CloudFormation::WaitConditionHandle: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-waitconditionhandle.html
.. _AWS::CloudFormation::Stack: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-stack.html
.. _AWS::S3::Bucket: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-s3-bucket.html
.. _InputParameters: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/parameters-section-structure.html
.. _troposphere: https://github.com/cloudtools/troposphere
.. _RollbackOnFailure: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cfn-console-add-tags.html?icmpid=docs_cfn_console
.. _SystemLog: http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-console.html#instance-console-console-output
.. _InstallerS3Bucket: https://s3.amazonaws.com/installer.downloads.clusterhq.com/flocker-cluster.cloudformation.json

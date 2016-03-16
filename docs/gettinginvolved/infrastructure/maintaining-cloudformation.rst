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

The :ref:`"Update the CloudFormation installer template"<release-process-cloudformation>` section of the release process demonstrates how to update the CloudFormation template and its AMI images.

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

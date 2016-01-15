FAQ for Maintainers
===================

What is the Installation Platform?
----------------------------------

Installer uses AWS CloudFormation to deploy {Flocker, Docker, Swarm} stack. Agent and Control node instances are m3.large EEC2 instances.

We use troposphere package to generate CloudFormation template.

How does CloudFormation work?
-----------------------------

CloudFormation takes in input template composed of resources. The template is manifested as a stack on AWS. Each resource is monitored to transition from ``CREATE_IN_PROGRESS`` to ``CREATE_COMPLETE`` state. Once all template resources reach ``CREATE_COMPLETE``, the stack is declared as ``CREATE_COMPLETE``. At this point, ``Outputs`` tab in CloudFormation is populated with necessary information to connect to and use the stack.

The following resource types are used for stack resources:
`AWS::EC2::Instance`_ - Agent Node, Control Node, Client Node
`AWS::S3::Bucket`_ - S3 bucket used to distribute config files

CloudFormation allows setting resource dependecies (start creating Resource A after Resource B is created). We use this feature to set Agent Node(s) and Client Node to be dependent on Control Node.

Control Node hosts Flocker Control Agent and Swarm Manager. Control Node is also responsible for certification generation for Flocker, Docker, and Swarm. We use an S3 bucket to broker certificate distribution: Control Node uploads Flocker certificates and agent yml to the bucket; Agent Node(s) and Client Node download Flocker configuration from the bucket. For Docker TLS, we upload Certificate Authority to the bucket. Agent Node(s) and Client Node create ceritificates for themselves using the CA downloaded from S3.

Why is there a wrapper around S3 commands?
------------------------------------------

Startup dependency for Agent Node(s) and Client Node on Control Node only ensures that these nodes' EC2 instances are started after Control Node EC2 instance is booted up. This dependecy does not account for post-boot time taken by Control Agent to populate S3 bucket. Hence, the wait and retry loop around S3 commands to allow Agent Node(s) and Client Node wait for S3 bucket to be populated with data by Control Node.

What happens if CloudFormation fails to bring up the stack?
----------------------------------------------------------

If any of the resources corresponding to the stack fail to reach ``CREATE_COMPLETE``, the stack is automatically rolled back. As a result, the user gets a functional stack or no stack.

How are {Flocker, Docker, Swarm} configured?
--------------------------------------------

Once `AWS::EC2::Instance`_ for agent/control node boots up, CloudFormation allows you to run user defined scripts as part of `UserData`_ cloud-init field. We plugin {Flocker, Docker, Swarm} install bash scripts into `UserData`_.

What happens if {Flocker, Docker, Swarm} configuration fails?
-------------------------------------------------------------

We use an `AWS::CloudFormation::WaitCondition`_ resource and a corresponding `AWS::CloudFormation::WaitConditionHandle`_ to wait for `UserData`_ configuration to complete. At the end of `UserData`_ script, we signal the WaitConditionHandle. This transitions the WaitCondition resource from ``CREATE_IN_PROGRESS`` to ``CREATE_COMPLETE`` state. The stack resource (`AWS::CloudFormation::Stack`_) is now unblocked to transition to ``CREATE_COMPLETE`` state.

If the `UserData`_ configuration fails, or takes longer than 600 seconds, WaitCondition transitions to `CREATE_FAILED` state, triggering a rollback of the stack.

.. _UserData: http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-metadata.html#instancedata-add-user-data
.. _AWS::EC2::Instance: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-ec2-instance.html
.. _AWS::CloudFormation::WaitCondition: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-waitcondition.html
.. _AWS::CloudFormation::WaitConditionHandle: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-waitconditionhandle.html
.. _AWS::CloudFormation::Stack: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-stack.html
.. _AWS::S3::Bucket: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-s3-bucket.html

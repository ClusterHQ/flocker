FAQ for Maintainers
===================

What is the Installation Platform?
----------------------------------

Installer uses AWS CloudFormation to deploy {Flocker, Docker, Swarm} stack. Agent and Control node instances are m3.large EC2 instances.

We use `troposphere`_ package to generate CloudFormation template.

How does CloudFormation work?
-----------------------------

CloudFormation takes in input template composed of resources. The template is manifested as a stack on AWS. Each resource is monitored to transition from ``CREATE_IN_PROGRESS`` to ``CREATE_COMPLETE`` state. Once all template resources reach ``CREATE_COMPLETE``, the stack is declared as ``CREATE_COMPLETE``. At this point, ``Outputs`` tab in CloudFormation is populated with necessary information to connect to and use the stack.

The following resource types are used for stack resources:
`AWS::EC2::Instance`_ - Agent Node, Control Node, Client Node
`AWS::S3::Bucket`_ - S3 bucket used to distribute config files

CloudFormation allows setting resource dependecies (start creating Resource A after Resource B is created). We use this feature to set Agent Node(s) and Client Node to be dependent on Control Node.

Control Node hosts Flocker Control Agent and Swarm Manager. Control Node is also responsible for certification generation for Flocker, Docker, and Swarm. We use an S3 bucket to broker certificate distribution: Control Node uploads Flocker certificates and agent yml to the bucket; Agent Node(s) and Client Node download Flocker configuration from the bucket. For Docker TLS, we upload Certificate Authority to the bucket. Agent Node(s) and Client Node create ceritificates for themselves using the CA downloaded from S3.

How are user-specific inputs (like AWS AccessKeyID) sourced?
------------------------------------------------------------

User's AWS ``AccessKeyID``, ``SecretAccessKey``, and ``KeyName`` are sourced as `InputParameters`_ in CloudFormation template.

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

How do i debug a failed stack creation?
---------------------------------------

By default, failure to bring up any of stack components rolls back the stack. Since the primary audience of the stack is potential customers, we want to give them a fully functional stack or not stack.

If you want to test new additions to the installer, and want to preserve stack state upon failure, please set `RollbackOnFailure`_ option to ``No`` during stack creation time.

One of my stack nodes failed to bring up Flocker/Docker/Swarm. How do i debug?
------------------------------------------------------------------------------

On the corresponding EC2 instance, please look at ``/var/log/cloud-init-output.log`` to triage which stage of `UserData`_ failed. The `UserData`_ script for this instance is located at ``/var/lib/cloud/instance/user-data.txt``.

```
root@ip-172-31-0-121:/var/log# tail /var/log/cloud-init-output.log 
< Date: Thu, 14 Jan 2016 19:32:17 GMT
< x-amz-version-id: PSDeN4p4VIsbZIiEDmpLpOTB9IKgYflW
< ETag: "5415af9707473d357f1e49108e428b1a"
< Content-Length: 0
* Server AmazonS3 is not blacklisted
  < Server: AmazonS3
  < 
  100   121    0     0  100   121      0    836 --:--:-- --:--:-- --:--:--   840
        * Connection #0 to host cloudformation-waitcondition-us-east-1.s3.amazonaws.com left intact
          Cloud-init v. 0.7.5 finished at Thu, 14 Jan 2016 19:32:16 +0000. Datasource DataSourceEc2.  Up 111.13 seconds
root@ip-172-31-0-121:/var/log#
```

``/var/lib/cloud/instance/user-data.txt`` can also be handy while prototyping enchancements to the installer. For example, if you would like to add Kubernetes as the scheduler, edit ``/var/lib/cloud/instance/user-data.txt`` to add Kubernetes setup, test on the EC2 instance, then add the working bash script to ``cloudformation.py``.

.. _UserData: http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-metadata.html#instancedata-add-user-data
.. _AWS::EC2::Instance: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-ec2-instance.html
.. _AWS::CloudFormation::WaitCondition: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-waitcondition.html
.. _AWS::CloudFormation::WaitConditionHandle: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-waitconditionhandle.html
.. _AWS::CloudFormation::Stack: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-stack.html
.. _AWS::S3::Bucket: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-s3-bucket.html
.. _InputParameters: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/parameters-section-structure.html
.. _troposphere: https://github.com/cloudtools/troposphere
.. _RollbackOnFailure: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cfn-console-add-tags.html?icmpid=docs_cfn_console

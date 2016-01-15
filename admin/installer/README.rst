FAQ for Maintainers
===================

What is the Installation Platform?
----------------------------------

Installer uses AWS CloudFormation to deploy {Flocker, Docker, Swarm} stack. Agent and Control node instances are m3.large EEC2 instances.

We use troposphere package to generate CloudFormation template.

How does CloudFormation work?
-----------------------------

CloudFormation takes in input template composed of resources. The template is manifested as a stack on AWS. Each resource is monitored to transition from `CREATE_IN_PROGRESS` to `CREATE_COMPLETE` state. Once all template resources reach `CREATE_COMPLETE`, the stack is declared as `CREATE_COMPLETE`. At this point, `Outputs` tab in CloudFormation is populated with necessary information to connect to and use the stack.

The following resource types are used for stack resources:
`AWS::EC2::Instance` - Agent Node, Control Node
`AWS::S3::Bucket` - S3 bucket used to distribute config files
`

What happens if CloudFormation fails to bring up the stack?
----------------------------------------------------------

If any of the resources corresponding to the stack fail to reach `CREATE_COMPLETE`, the stack is automatically rolled back. So, the user gets a functional stack or no stack.

How are {Flocker, Docker, Swarm} configured?
--------------------------------------------

Once `AWS::EC2::Instance` for agent/control node boots up, CloudFormation allows you to run user defined scripts as part of `UserData` cloud-init field. We plugin {Flocker, Docker, Swarm} install bash scripts into `UserData`.

What happens if {Flocker, Docker, Swarm} configuration fails?
-------------------------------------------------------------

We use an `AWS::CloudFormation::WaitCondition` resource and a corresponding `AWS::CloudFormation::WaitConditionHandle` to wait for `UserData` configuration to complete. At the end of `UserData` script, we signal the WaitConditionHandle. This transitions the WaitCondition resource from `CREATE_IN_PROGRESS` to `CREATE_COMPLETE` state. The stack resource (`AWS::CloudFormation::Stack`) is now unblocked to transition to `CREATE_COMPLETE` state.

If the `UserData` configuration fails, or takes longer than 600 seconds, WaitCondition transitions to `CREATE_FAILED` state, triggering a rollback of the stack.


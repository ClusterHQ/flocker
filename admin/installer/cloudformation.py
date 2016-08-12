# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Troposphere script to generate an AWS CloudFormation JSON template.

Sample usage:

    admin/create-cloudformation-template \
        --client-ami-map-body="$(<ami_map_docker.json)" \
        --node-ami-map-body="$(<ami_map_flocker.json)" \
        > "flocker-cluster.cloudformation.json"

Resulting JSON template has the following blueprint to describe the
desired stack's resources and properties:

* 1 Control Node with Flocker Control Service, (TLS-enabled) Swarm Manager,
  (TLS-enabled) Docker, Ubuntu 16.04

  After Control Node is booted, proceed with creating rest of the stack.

* 2 Agent Nodes with Flocker Dataset Agent, Swarm Agent, (TLS-enabled) Docker,
  Ubuntu 16.04

  After Agent Nodes are booted and configured with Flocker and Swarm, proceed
  with creating rest of the stack.

* 1 Client Node with Flockerctl, Docker, Docker-compose, Ubuntu 16.04

To manifest the blueprint, please input the JSON template at AWS CloudFormation
Create Stack console (after replacing ``us-east-1`` with your Region):
https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/new
"""

import argparse
import os
import json

from troposphere import FindInMap, GetAtt, Base64, Join, Tags
from troposphere import Parameter, Output, Ref, Template, GetAZs, Select
from troposphere.s3 import Bucket
import troposphere.ec2 as ec2
from troposphere.cloudformation import WaitConditionHandle, WaitCondition

MIN_CLUSTER_SIZE = 3
MAX_CLUSTER_SIZE = 10
DEFAULT_CLUSTER_SIZE = MIN_CLUSTER_SIZE

NODE_CONFIGURATION_TIMEOUT = u"900"
AGENT_NODE_NAME_TEMPLATE = u"AgentNode{index}"
EC2_INSTANCE_NAME_TEMPLATE = u"{stack_name}_{node_type}"
CONTROL_NODE_NAME = u"ControlNode"
CLIENT_NODE_NAME = u"ClientNode"
INFRA_WAIT_HANDLE_TEMPLATE = u"{node}FlockerSwarmReadySignal"
INFRA_WAIT_CONDITION_TEMPLATE = u"{node}FlockerSwarmSetup"
CLIENT_WAIT_HANDLE = u"ClientReadySignal"
CLIENT_WAIT_CONDITION = u"ClientSetup"
S3_SETUP = 'setup_s3.sh'
DOCKER_SETUP = 'setup_docker.sh'
DOCKER_SWARM_CA_SETUP = 'docker-swarm-ca-setup.sh'
SWARM_MANAGER_SETUP = 'setup_swarm_manager.sh'
SWARM_NODE_SETUP = 'setup_swarm_node.sh'
VOLUMEHUB_SETUP = 'setup_volumehub.sh'
FLOCKER_CONFIGURATION_GENERATOR = 'flocker-configuration-generator.sh'
FLOCKER_CONFIGURATION_GETTER = 'flocker-configuration-getter.sh'
CLIENT_SETUP = 'setup_client.sh'
SIGNAL_CONFIG_COMPLETION = 'signal_config_completion.sh'


def _validate_cluster_size(size):
    """
    Validate that user-input cluster size is supported by Installer.

    :param int size: Desired number of nodes in the cluster.
    :raises: InvalidClusterSizeException,
             if input cluster size is unsupported.
    :returns: Validated cluster size.
    :rtype: int
    """
    try:
        size = int(size)
    except ValueError:
        raise argparse.ArgumentTypeError(
            u"Must be an integer. Found {!r}".format(
                size
            )
        )

    if size < MIN_CLUSTER_SIZE or size > MAX_CLUSTER_SIZE:
        raise argparse.ArgumentTypeError(
            u"Must be between {} and {}. Found {}.".format(
                MIN_CLUSTER_SIZE, MAX_CLUSTER_SIZE, size
            )
        )
    return size


def create_cloudformation_template_options():
    """
    :returns: A command line option parser for
        `admin/create-cloudformation-template`.
    """
    parser = argparse.ArgumentParser(
        description=(
            u'Create a CloudFormation template '
            u'for a Flocker cluster used in the '
            u'Docker, Swarm, Compose installation instructions.'
        )
    )

    parser.add_argument(
        u'--cluster-size',
        default=MIN_CLUSTER_SIZE,
        type=_validate_cluster_size,
        help=(
            u'An integer corresponding to desired '
            u'number of nodes in the cluster. '
            u'Supported sizes: min={0}, max={1}'
        ).format(
            MIN_CLUSTER_SIZE,
            MAX_CLUSTER_SIZE
        )
    )

    parser.add_argument(
        u'--client-ami-map-body',
        type=json.loads,
        help=u'A JSON map of AWS region to AMI ID for client.',
        dest='client_ami_map',
        required=True,
    )

    parser.add_argument(
        u'--node-ami-map-body',
        type=json.loads,
        help=u'A JSON map of AWS region to AMI ID for nodes.',
        dest='node_ami_map',
        required=True,
    )

    return parser


def create_cloudformation_template_main(argv, basepath, toplevel):
    """
    The entry point for `admin/create-cloudformation-template`.
    """
    parser = create_cloudformation_template_options()
    options = parser.parse_args(argv)

    print flocker_docker_template(
        cluster_size=options.cluster_size,
        client_ami_map=options.client_ami_map,
        node_ami_map=options.node_ami_map,
    )


def _sibling_lines(filename):
    """
    Read file content into an output string.
    """
    dirname = os.path.dirname(__file__)
    path = os.path.join(dirname, filename)
    with open(path, 'r') as f:
        return f.readlines()


def flocker_docker_template(cluster_size, client_ami_map, node_ami_map):
    """
    :param int cluster_size: The number of nodes to create in the Flocker
        cluster (including control service node).
    :param dict client_ami_map: A map between AWS region name and AWS AMI ID
        for the client.
    :param dict node_ami_map: A map between AWS region name and AWS AMI ID
        for the node.
    :returns: a CloudFormation template for a Flocker + Docker + Docker Swarm
        cluster.
    """
    # Base JSON template.
    template = Template()

    # Keys corresponding to CloudFormation user Inputs.
    access_key_id_param = template.add_parameter(Parameter(
        "AmazonAccessKeyID",
        Description="Required: Your Amazon AWS access key ID",
        Type="String",
        NoEcho=True,
        AllowedPattern="[\w]+",
        MinLength="16",
        MaxLength="32",
    ))
    secret_access_key_param = template.add_parameter(Parameter(
        "AmazonSecretAccessKey",
        Description="Required: Your Amazon AWS secret access key",
        Type="String",
        NoEcho=True,
        MinLength="1",
    ))
    keyname_param = template.add_parameter(Parameter(
        "EC2KeyPair",
        Description="Required: Name of an existing EC2 KeyPair to enable SSH "
                    "access to the instance",
        Type="AWS::EC2::KeyPair::KeyName",
    ))
    template.add_parameter(Parameter(
        "S3AccessPolicy",
        Description="Required: Is current IAM user allowed to access S3? "
                    "S3 access is required to distribute Flocker and Docker "
                    "configuration amongst stack nodes. Reference: "
                    "http://docs.aws.amazon.com/IAM/latest/UserGuide/"
                    "access_permissions.html Stack creation will fail if user "
                    "cannot access S3",
        Type="String",
        AllowedValues=["Yes"],
    ))
    volumehub_token = template.add_parameter(Parameter(
        "VolumeHubToken",
        Description=(
            "Optional: Your Volume Hub token. "
            "You'll find the token at "
            "https://volumehub.clusterhq.com/v1/token."
        ),
        Type="String",
        Default="",
    ))

    template.add_mapping(
        'RegionMapClient', {
            k: {"AMI": v} for k, v in client_ami_map.items()
        }
    )
    template.add_mapping(
        'RegionMapNode', {
            k: {"AMI": v} for k, v in node_ami_map.items()
        }
    )

    # Select a random AvailabilityZone within given AWS Region.
    zone = Select(0, GetAZs(""))

    # S3 bucket to hold {Flocker, Docker, Swarm} configuration for distribution
    # between nodes.
    s3bucket = Bucket('ClusterConfig',
                      DeletionPolicy='Retain')
    template.add_resource(s3bucket)

    # Create SecurityGroup for cluster instances.
    instance_sg = template.add_resource(
        ec2.SecurityGroup(
            "InstanceSecurityGroup",
            GroupDescription=(
                "Enable ingress access on all protocols and ports."
            ),
            SecurityGroupIngress=[
                ec2.SecurityGroupRule(
                    IpProtocol=protocol,
                    FromPort="0",
                    ToPort="65535",
                    CidrIp="0.0.0.0/0",
                ) for protocol in ('tcp', 'udp')
            ]
        )
    )

    # Base for post-boot {Flocker, Docker, Swarm} configuration on the nodes.
    base_user_data = [
        '#!/bin/bash\n',
        'aws_region="', Ref("AWS::Region"), '"\n',
        'aws_zone="', zone, '"\n',
        'access_key_id="', Ref(access_key_id_param), '"\n',
        'secret_access_key="', Ref(secret_access_key_param), '"\n',
        's3_bucket="', Ref(s3bucket), '"\n',
        'stack_name="', Ref("AWS::StackName"), '"\n',
        'volumehub_token="', Ref(volumehub_token), '"\n',
        'node_count="{}"\n'.format(cluster_size),
        'apt-get update\n',
    ]

    # XXX Flocker agents are indexed from 1 while the nodes overall are indexed
    # from 0.
    flocker_agent_number = 1

    # Gather WaitConditions
    wait_condition_names = []

    for i in range(cluster_size):
        if i == 0:
            node_name = CONTROL_NODE_NAME
        else:
            node_name = AGENT_NODE_NAME_TEMPLATE.format(index=i)

        # Create an EC2 instance for the {Agent, Control} Node.
        ec2_instance = ec2.Instance(
            node_name,
            ImageId=FindInMap("RegionMapNode", Ref("AWS::Region"), "AMI"),
            InstanceType="m3.large",
            KeyName=Ref(keyname_param),
            SecurityGroups=[Ref(instance_sg)],
            AvailabilityZone=zone,
            Tags=Tags(Name=node_name))

        # WaitCondition and corresponding Handler to signal completion
        # of {Flocker, Docker, Swarm} configuration on the node.
        wait_condition_handle = WaitConditionHandle(
            INFRA_WAIT_HANDLE_TEMPLATE.format(node=node_name))
        template.add_resource(wait_condition_handle)
        wait_condition = WaitCondition(
            INFRA_WAIT_CONDITION_TEMPLATE.format(node=node_name),
            Handle=Ref(wait_condition_handle),
            Timeout=NODE_CONFIGURATION_TIMEOUT,
        )
        template.add_resource(wait_condition)

        # Gather WaitConditions
        wait_condition_names.append(wait_condition.name)

        user_data = base_user_data[:]
        user_data += [
            'node_number="{}"\n'.format(i),
            'node_name="{}"\n'.format(node_name),
            'wait_condition_handle="', Ref(wait_condition_handle), '"\n',
        ]

        # Setup S3 utilities to push/pull node-specific data to/from S3 bucket.
        user_data += _sibling_lines(S3_SETUP)

        if i == 0:
            # Control Node configuration.
            control_service_instance = ec2_instance
            user_data += ['flocker_node_type="control"\n']
            user_data += _sibling_lines(FLOCKER_CONFIGURATION_GENERATOR)
            user_data += _sibling_lines(DOCKER_SWARM_CA_SETUP)
            user_data += _sibling_lines(DOCKER_SETUP)

            # Setup Swarm 1.0.1
            user_data += _sibling_lines(SWARM_MANAGER_SETUP)
            template.add_output([
                Output(
                    "ControlNodeIP",
                    Description="Public IP of Flocker Control and "
                                "Swarm Manager.",
                    Value=GetAtt(ec2_instance, "PublicIp"),
                )
            ])
        else:
            # Agent Node configuration.
            ec2_instance.DependsOn = control_service_instance.name
            user_data += [
                'flocker_node_type="agent"\n',
                'flocker_agent_number="{}"\n'.format(
                    flocker_agent_number
                )
            ]
            flocker_agent_number += 1
            user_data += _sibling_lines(DOCKER_SETUP)

            # Setup Swarm 1.0.1
            user_data += _sibling_lines(SWARM_NODE_SETUP)
            template.add_output([
                Output(
                    "AgentNode{}IP".format(i),
                    Description=(
                        "Public IP of Agent Node for Flocker and Swarm."
                    ),
                    Value=GetAtt(ec2_instance, "PublicIp"),
                )
            ])

        user_data += _sibling_lines(FLOCKER_CONFIGURATION_GETTER)
        user_data += _sibling_lines(VOLUMEHUB_SETUP)
        user_data += _sibling_lines(SIGNAL_CONFIG_COMPLETION)
        ec2_instance.UserData = Base64(Join("", user_data))
        template.add_resource(ec2_instance)

    # Client Node creation.
    client_instance = ec2.Instance(
        CLIENT_NODE_NAME,
        ImageId=FindInMap("RegionMapClient", Ref("AWS::Region"), "AMI"),
        InstanceType="m3.medium",
        KeyName=Ref(keyname_param),
        SecurityGroups=[Ref(instance_sg)],
        AvailabilityZone=zone,
        Tags=Tags(Name=CLIENT_NODE_NAME))
    wait_condition_handle = WaitConditionHandle(CLIENT_WAIT_HANDLE)
    template.add_resource(wait_condition_handle)
    wait_condition = WaitCondition(
        CLIENT_WAIT_CONDITION,
        Handle=Ref(wait_condition_handle),
        Timeout=NODE_CONFIGURATION_TIMEOUT,
    )
    template.add_resource(wait_condition)

    # Client Node {Flockerctl, Docker-compose} configuration.
    user_data = base_user_data[:]
    user_data += [
        'wait_condition_handle="', Ref(wait_condition_handle), '"\n',
        'node_number="{}"\n'.format("-1"),
    ]
    user_data += _sibling_lines(S3_SETUP)
    user_data += _sibling_lines(CLIENT_SETUP)
    user_data += _sibling_lines(SIGNAL_CONFIG_COMPLETION)
    client_instance.UserData = Base64(Join("", user_data))

    # Start Client Node after Control Node and Agent Nodes are
    # up and running Flocker, Docker, Swarm stack.
    client_instance.DependsOn = wait_condition_names
    template.add_resource(client_instance)

    # List of Output fields upon successful creation of the stack.
    template.add_output([
        Output(
            "ClientNodeIP",
            Description="Public IP address of the client node.",
            Value=GetAtt(client_instance, "PublicIp"),
        )
    ])
    template.add_output(Output(
        "ClientConfigDockerSwarmHost",
        Value=Join("",
                   ["export DOCKER_HOST=tcp://",
                    GetAtt(control_service_instance, "PublicIp"), ":2376"]),
        Description="Client config: Swarm Manager's DOCKER_HOST setting."
    ))
    template.add_output(Output(
        "ClientConfigDockerTLS",
        Value="export DOCKER_TLS_VERIFY=1",
        Description="Client config: Enable TLS client for Swarm."
    ))
    return template.to_json()

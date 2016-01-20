"""
Troposphere script to generate an AWS CloudFormation JSON template.

Sample usage:
python cloudformation.py > /tmp/flocker-cluster.cloudformation.json

Resulting JSON template has the following blueprint to describe the
desired stack's resources and properties:
1 Control Node with Flocker Control Service, (TLS-enabled) Swarm Manager,
                    (TLS-enabled) Docker, Ubuntu 14.04
2 Agent Nodes with Flocker Dataset Agent, Swarm Agent, (TLS-enabled) Docker,
                   Ubuntu 14.04
1 Client Node with Flockerctl, Docker, Docker-compose, Ubuntu 14.04

To manifest the blueprint, please input the JSON template at AWS CloudFormation
Create Stack console (after replacing ``us-east-1`` with your Region):
https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/new
"""

import os

from troposphere import FindInMap, GetAtt, Base64, Join, Tags
from troposphere import Parameter, Output, Ref, Template, GetAZs, Select
from troposphere.s3 import Bucket
import troposphere.ec2 as ec2
from troposphere.cloudformation import WaitConditionHandle, WaitCondition

NUM_NODES = 3
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


def _sibling_lines(filename):
    """
    Read file content into an output string.
    """
    dirname = os.path.dirname(__file__)
    path = os.path.join(dirname, filename)
    with open(path, 'r') as f:
        return f.readlines()

# Base JSON template.
template = Template()

# Keys corresponding to CloudFormation user Inputs.
keyname_param = template.add_parameter(Parameter(
    "KeyPair",
    Description="Name of an existing EC2 KeyPair to enable SSH "
                "access to the instance",
    Type="String",
))
access_key_id_param = template.add_parameter(Parameter(
    "AccessKeyID",
    Description="Your Amazon AWS access key ID",
    Type="String",
))
secret_access_key_param = template.add_parameter(Parameter(
    "SecretAccessKey",
    Description="Your Amazon AWS secret access key.",
    Type="String",
))

volumehub_token = template.add_parameter(Parameter(
    "VolumeHubToken",
    Description=(
        "Your Volume Hub token. "
        "You'll find the token at https://volumehub.clusterhq.com/v1/token."
    ),
    Type="String",
))

# Base AMIs pre-baked with the following products:
# Docker 1.9.1
# Flocker 1.9.0.dev1+1221.gde4c49f
# Please update the version fields above when new AMIs are generated.
template.add_mapping(
    'RegionMap', {
        'us-east-1':      {"FlockerAMI": "ami-d81b3eb2",
                           "ClientAMI": "ami-c61e3bac"},
        'us-west-1':      {"FlockerAMI": "ami-2e10644e",
                           "ClientAMI": "ami-aa1064ca"},
        'us-west-2':      {"FlockerAMI": "ami-51879d30",
                           "ClientAMI": "ami-8dbaa0ec"},
        'eu-west-1':      {"FlockerAMI": "ami-6358f310",
                           "ClientAMI": "ami-ef5bf09c"},
        'eu-central-1':   {"FlockerAMI": "ami-32574e5e",
                           "ClientAMI": "ami-6c544d00"},
        'sa-east-1':      {"FlockerAMI": "ami-e4b73688",
                           "ClientAMI": "ami-fdb43591"},
        'ap-northeast-1': {"FlockerAMI": "ami-e71e2289",
                           "ClientAMI": "ami-1a211d74"},
        'ap-southeast-1': {"FlockerAMI": "ami-1bc10d78",
                           "ClientAMI": "ami-cbc20ea8"},
        'ap-southeast-2': {"FlockerAMI": "ami-c00b2ea3",
                           "ClientAMI": "ami-c20b2ea1"},
    }
)

instances = []

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
        GroupDescription="Enable ingress access on all protocols and ports.",
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
    'node_count="{}"\n'.format(NUM_NODES),
    'apt-get update\n',
]

# XXX Flocker agents are indexed from 1 while the nodes overall are indexed
# from 0.
flocker_agent_number = 1

for i in range(NUM_NODES):
    if i == 0:
        node_name = CONTROL_NODE_NAME
    else:
        node_name = AGENT_NODE_NAME_TEMPLATE.format(index=i)

    # Create an EC2 instance for the {Agent, Control} Node.
    ec2_instance = ec2.Instance(
        node_name,
        ImageId=FindInMap("RegionMap", Ref("AWS::Region"), "FlockerAMI"),
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
        Timeout="600",
    )
    template.add_resource(wait_condition)

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
        user_data += 'flocker_node_type="control"\n',
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
        user_data += 'flocker_node_type="agent"\n'
        user_data += 'flocker_agent_number="{}"\n'.format(
            flocker_agent_number
        )
        flocker_agent_number += 1
        user_data += _sibling_lines(DOCKER_SETUP)

        # Setup Swarm 1.0.1
        user_data += _sibling_lines(SWARM_NODE_SETUP)
        template.add_output([
            Output(
                "AgentNode{}IP".format(i),
                Description="Public IP of Agent Node for Flocker and Swarm.",
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
    ImageId=FindInMap("RegionMap", Ref("AWS::Region"), "ClientAMI"),
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
    Timeout="600",
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
client_instance.DependsOn = control_service_instance.name
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
template.add_output(Output(
    "S3Bucket",
    Value=Ref(s3bucket),
    Description="Name of S3 bucket to hold cluster configuration files."
))
print(template.to_json())

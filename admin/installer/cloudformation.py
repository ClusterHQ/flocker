# Converted from EC2InstanceSample.template located at:
# http://aws.amazon.com/cloudformation/aws-cloudformation-templates/
import json
import os
import re
import urllib

from troposphere import FindInMap, GetAtt, Base64, Join
from troposphere import Parameter, Output, Ref, Template, GetAZs, Select
from troposphere.s3 import Bucket
import troposphere.ec2 as ec2
from troposphere.cloudformation import WaitConditionHandle, WaitCondition

NUM_NODES = 3
AGENT_NODE_NAME_TEMPLATE = u"AgentNode{index}"
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
FLOCKER_CONFIGURATION_GENERATOR = 'flocker-configuration-generator.sh'
FLOCKER_CONFIGURATION_GETTER = 'flocker-configuration-getter.sh'
CLIENT_SETUP = 'setup_client.sh'
SIGNAL_CONFIG_COMPLETION = 'signal_config_completion.sh'


def sibling_lines(filename):
    dirname = os.path.dirname(__file__)
    path = os.path.join(dirname, filename)
    with open(path, 'r') as f:
        return f.readlines()

template = Template()

keyname_param = template.add_parameter(Parameter(
    "KeyName",
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

template.add_mapping(
    'RegionMap', {
        'us-east-1':      {"FlockerAMI": "ami-5f401635",
                           "ClientAMI": "ami-86590fec"},
        'us-west-1':      {"FlockerAMI": "ami-e83a5088",
                           "ClientAMI": "ami-0a254f6a"},
        'us-west-2':      {"FlockerAMI": "ami-bd2b35dc",
                           "ClientAMI": "ami-fa2b359b"},
    }
)

instances = []
zone = Select(0, GetAZs(""))

s3bucket = Bucket('ClusterConfig',
                  DeletionPolicy='Retain')
template.add_resource(s3bucket)

# Create SecurityGroup for cluster instances
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
base_user_data = [
    '#!/bin/bash\n',
    'aws_region="', Ref("AWS::Region"), '"\n',
    'aws_zone="', zone, '"\n',
    'access_key_id="', Ref(access_key_id_param), '"\n',
    'secret_access_key="', Ref(secret_access_key_param), '"\n',
    's3_bucket="', Ref(s3bucket), '"\n',
    'stack_name="', Ref("AWS::StackName"), '"\n',
    'node_count="{}"\n'.format(NUM_NODES),
    'apt-get update\n',
]

for i in range(NUM_NODES):
    if i == 0:
        node_name = CONTROL_NODE_NAME
    else:
        node_name = AGENT_NODE_NAME_TEMPLATE.format(index=i)

    ec2_instance = ec2.Instance(
        node_name,
        ImageId=FindInMap("RegionMap", Ref("AWS::Region"), "FlockerAMI"),
        InstanceType="m3.large",
        KeyName=Ref(keyname_param),
        SecurityGroups=[Ref(instance_sg)],
        AvailabilityZone=zone,
    )

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

    user_data += sibling_lines(S3_SETUP)

    if i == 0:
        control_service_instance = ec2_instance
        user_data += sibling_lines(FLOCKER_CONFIGURATION_GENERATOR)
        user_data += sibling_lines(DOCKER_SWARM_CA_SETUP)
        user_data += sibling_lines(DOCKER_SETUP)
        user_data += sibling_lines(SWARM_MANAGER_SETUP)
        template.add_output([
            Output(
                "ControlNodeIP",
                Description="Public IP of Flocker Control and "
                            "Swarm Manager.",
                Value=GetAtt(ec2_instance, "PublicIp"),
            )
        ])
    else:
        ec2_instance.DependsOn = control_service_instance.name
        user_data += sibling_lines(DOCKER_SETUP)
        user_data += sibling_lines(SWARM_NODE_SETUP)
        template.add_output([
            Output(
                "AgentNode{}IP".format(i),
                Description="Public IP of Agent Node for Flocker and Swarm.",
                Value=GetAtt(ec2_instance, "PublicIp"),
            )
        ])

    user_data += sibling_lines(FLOCKER_CONFIGURATION_GETTER)
    user_data += sibling_lines(SIGNAL_CONFIG_COMPLETION)
    ec2_instance.UserData = Base64(Join("", user_data))
    template.add_resource(ec2_instance)

client_instance = ec2.Instance(
    CLIENT_NODE_NAME,
    ImageId=FindInMap("RegionMap", Ref("AWS::Region"), "ClientAMI"),
    InstanceType="m3.large",
    KeyName=Ref(keyname_param),
    SecurityGroups=[Ref(instance_sg)],
    AvailabilityZone=zone,
)
wait_condition_handle = WaitConditionHandle(CLIENT_WAIT_HANDLE)
template.add_resource(wait_condition_handle)
wait_condition = WaitCondition(
    CLIENT_WAIT_CONDITION,
    Handle=Ref(wait_condition_handle),
    Timeout="600",
)
template.add_resource(wait_condition)

user_data = base_user_data[:]
user_data += [
    'wait_condition_handle="', Ref(wait_condition_handle), '"\n',
    'node_number="{}"\n'.format("-1"),
]
user_data += sibling_lines(S3_SETUP)
user_data += sibling_lines(DOCKER_SETUP)
user_data += sibling_lines(CLIENT_SETUP)
user_data += sibling_lines(SIGNAL_CONFIG_COMPLETION)

client_instance.UserData = Base64(Join("", user_data))
client_instance.DependsOn = control_service_instance.name

template.add_resource(client_instance)

template.add_output([
    Output(
        "ClientNodeIP",
        Description="Public IP address of the client node.",
        Value=GetAtt(client_instance, "PublicIp"),
    )
])

template.add_output(Output(
    "ClientDockerConfiguration",
    Value=Join("",
               ["Swarm DOCKER_HOST: ",
                GetAtt(control_service_instance, "PublicIp"), ":2376",
                "TLS certificate location: /root/.docker"]),
    Description="Client configuration to communicate with Swarm Manager."
))

base_url = "https://resources.console.aws.amazon.com/r/group#sharedgroup="
parameters = {
    "name": "%STACK_NAME%",
    "regions": "all",
    "resourceTypes": "all",
    "tagFilters": [
        {
            "key": "aws:cloudformation:stack-name",
            "values": [
                "%STACK_NAME%"
            ]
        }
    ]
}

parameter_string = json.dumps(parameters, separators=(',', ':'))

variables = {
    "STACK_NAME": Ref('AWS::StackName')
}

pattern = r'%([A-Z_]+)%'
parts = re.split(pattern, parameter_string)
iparts = iter(parts)
new_parts = [base_url]
for part in iparts:
    new_parts.append(urllib.quote_plus(part))
    key = next(iparts, None)
    if key is not None:
        new_parts.append(variables[key])

template.add_output(Output(
    "CloudFormationStackView",
    Value=Join("", new_parts),
    Description="A view of all the resources in this stack."
))

print(template.to_json())

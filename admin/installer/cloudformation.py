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

NUM_NODES = 3
NODE_NAME_TEMPLATE = u"Flocker{index}"
S3_SETUP = 'setup_s3.sh'
DOCKER_SETUP = 'setup_docker.sh'
SWARM_MANAGER_SETUP = 'setup_swarm_manager.sh'
SWARM_NODE_SETUP = 'setup_swarm_node.sh'
FLOCKER_CONFIGURATION_GENERATOR = 'flocker-configuration-generator.sh'
FLOCKER_CONFIGURATION_GETTER = 'flocker-configuration-getter.sh'


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

template.add_mapping('RegionMap', {
    'us-east-1':      {"FlockerAMI": 'ami-dc4410b6'},
    'us-west-1':      {"FlockerAMI": 'ami-e098f380'},
    'us-west-2':      {"FlockerAMI": 'ami-8c8f90ed'},
})

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

for i in range(NUM_NODES):
    node_name = NODE_NAME_TEMPLATE.format(index=i)
    ec2_instance = ec2.Instance(
        node_name,
        ImageId=FindInMap("RegionMap", Ref("AWS::Region"), "FlockerAMI"),
        InstanceType="m3.large",
        KeyName=Ref(keyname_param),
        SecurityGroups=[Ref(instance_sg)],
        AvailabilityZone=zone,
    )
    user_data = [
        '#!/bin/bash\n',
        'aws_region="', Ref("AWS::Region"), '"\n',
        'aws_zone="', zone, '"\n',
        'access_key_id="', Ref(access_key_id_param), '"\n',
        'secret_access_key="', Ref(secret_access_key_param), '"\n',
        's3_bucket="', Ref(s3bucket), '"\n',
        'node_count="{}"\n'.format(NUM_NODES),
        'node_number="{}"\n'.format(i),
        'apt-get update\n',
    ]

    user_data += sibling_lines(DOCKER_SETUP)
    user_data += sibling_lines(S3_SETUP)

    if i == 0:
        control_service_instance = ec2_instance
        user_data += sibling_lines(FLOCKER_CONFIGURATION_GENERATOR)
        user_data += sibling_lines(SWARM_MANAGER_SETUP)
        template.add_output([
            Output(
                "FlockerControlIP",
                Description="Public IP address of the Flocker Control node.",
                Value=GetAtt(ec2_instance, "PublicIp"),
            )
        ])
    else:
        ec2_instance.DependsOn = control_service_instance.name
    template.add_output([
        Output(
            "FlockerNode{}IP".format(i),
            Description="Public IP address of a Flocker Agent node.",
            Value=GetAtt(ec2_instance, "PublicIp"),
        )
    ])

    user_data += sibling_lines(FLOCKER_CONFIGURATION_GETTER)
    user_data += sibling_lines(SWARM_NODE_SETUP)
    ec2_instance.UserData = Base64(Join("", user_data))

    template.add_resource(ec2_instance)


template.add_output([
    Output(
        "AvailabilityZone",
        Description="Availability Zone of the newly created EC2 instances.",
        Value=zone,
    ),
])
template.add_output(Output(
    "S3BucketName",
    Value=Ref(s3bucket),
    Description="Name of S3 bucket to hold cluster configuration files."
))
template.add_output(Output(
    "SwarmDockerHost",
    Value=Join("", ["export DOCKER_HOST=",
               GetAtt(control_service_instance, "PublicIp"), ":2376"]),
    Description="Please point DOCKER_HOST at Swarm Manager."
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
    "ResourceGroup",
    Value=Join("", new_parts),
    Description="A view of all the resources in this stack."
))

print(template.to_json())

# Converted from EC2InstanceSample.template located at:
# http://aws.amazon.com/cloudformation/aws-cloudformation-templates/

from troposphere import FindInMap, GetAtt, Base64
from troposphere.cloudformation import (
    Metadata, Init, InitConfig, InitFiles, InitFile
)
from troposphere import Parameter, Output, Ref, Template
import troposphere.ec2 as ec2

OWNER = u"richardw"
NUM_NODES = 1
NODE_NAME_TEMPLATE = u"{owner}flockerdemo{index}"

AGENT_YAML_TEMPLATE = """\
control-service:
    hostname: {control_node_ipaddress}
    port: 4524
dataset:
    access_key_id: {access_key_id}
    backend: aws
    region: {aws_region}
    secret_access_key: {secret_access_key}
    zone: {aws_zone}
version: 1
"""

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
    # richardw-test1 AMI generated from a running acceptance test node.
    "us-east-1":      {"AMI": "ami-6cabe306"},
})

instances = []
for i in range(NUM_NODES):
    node_name = NODE_NAME_TEMPLATE.format(owner=OWNER, index=i)
    ec2_instance = ec2.Instance(
        node_name,
        ImageId=FindInMap("RegionMap", Ref("AWS::Region"), "AMI"),
        InstanceType="m3.large",
        KeyName=Ref(keyname_param),
        SecurityGroups=["acceptance"],
    )
    ec2_instance.UserData=Base64('\n'.join([
            '#!/bin/bash',
            'cat <<EOF >/etc/flocker/agent.yml',
            AGENT_YAML_TEMPLATE.format(access_key_id=Ref(access_key_id_param),
                            secret_access_key=Ref(access_key_id_param),
                            control_node_ipaddress=GetAtt(
                                ec2_instance, "PublicIp"
                            ),
                            aws_region=Ref("AWS::Region"),
                            aws_zone=Ref("AWS::Zone"),
                        ),
           'EOF'
        ]))
    template.add_resource(ec2_instance)
    template.add_output([
        Output(
            "{}PublicIP".format(node_name),
            Description="Public IP address of the newly created EC2 instance",
            Value=GetAtt(ec2_instance, "PublicIp"),
        ),
        Output(
            "{}PublicDNS".format(node_name),
            Description="Public DNSName of the newly created EC2 instance",
            Value=GetAtt(ec2_instance, "PublicDnsName"),
        ),
    ])

template.add_output([
    Output(
        "AvailabilityZone",
        Description="Availability Zone of the newly created EC2 instance",
        Value=Ref("AWS::Region"),
    ),
])

print(template.to_json())

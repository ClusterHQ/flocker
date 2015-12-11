# Converted from EC2InstanceSample.template located at:
# http://aws.amazon.com/cloudformation/aws-cloudformation-templates/

from troposphere import Base64, FindInMap, GetAtt
from troposphere import Parameter, Output, Ref, Template
import troposphere.ec2 as ec2

OWNER = u"richardw"
NUM_NODES = 3
NODE_NAME_TEMPLATE = u"{owner}flockerdemo{index}"

template = Template()

keyname_param = template.add_parameter(Parameter(
    "KeyName",
    Description="Name of an existing EC2 KeyPair to enable SSH "
                "access to the instance",
    Type="String",
))

template.add_mapping('RegionMap', {
    # richardw-test1 AMI generated from a running acceptance test node.
    "us-west-1":      {"AMI": "ami-6cabe306"},
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
        UserData=Base64("80")
    )
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

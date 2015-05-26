# Copyright ClusterHQ Inc.  See LICENSE file for details.

from eliot import Field, ActionType, MessageType

OPERATION = Field.forTypes(
    u"operation", [list],
    u"The IBlockDeviceAPI command being executed, \
    along with positional and keyword arguments.")

AWS_ACTION = ActionType(
    u"flocker:node:agents:blockdevice:aws",
    [OPERATION],
    [],
    u"An IBlockDeviceAPI command is executing against EBS.")

# Begin: Scaffolding for logging Boto client and server exceptions
# via Eliot.
AWS_CODE = Field.for_types(
    "code", [bytes, unicode],
    u"The error response code.")
AWS_MESSAGE = Field.for_types(
    "message", [bytes, unicode],
    u"A human-readable error message given by the response.",
)
AWS_REQUEST_ID = Field.for_types(
    "request_id", [bytes, unicode],
    u"The unique identifier assigned by the server for this request.",
)

# Log boto.exception.BotoEC2ResponseError, covering all errors from AWS:
# server operation rate limit exceeded, invalid server request parameters, etc.
BOTO_EC2RESPONSE_ERROR = MessageType(
    u"boto:boto_ec2response_error", [
        AWS_CODE,
        AWS_MESSAGE,
        AWS_REQUEST_ID,
    ],
)

# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Helper module to provide macros for logging support
for storage drivers (AWS, Cinder).
See https://clusterhq.atlassian.net/browse/FLOC-2053
for consolidation opportunities.
"""

from eliot import Field, ActionType, MessageType

# Begin: Common structures used by all (AWS, OpenStack)
# storage drivers.

# An OPERATION is a list of:
# IBlockDeviceAPI name, positional arguments, keyword arguments.
OPERATION = Field.for_types(
    u"operation", [list],
    u"The IBlockDeviceAPI operation being executed,"
    u"along with positional and keyword arguments.")

# End: Common structures used by all storage drivers.

# Begin: Helper datastructures to log IBlockDeviceAPI calls
# from AWS storage driver using Eliot.

# ActionType used by AWS storage driver.
AWS_ACTION = ActionType(
    u"flocker:node:agents:blockdevice:aws",
    [OPERATION],
    [],
    u"An IBlockDeviceAPI operation is executing using AWS storage driver.")

# Three fields to gather from EC2 response to Boto.
AWS_CODE = Field.for_types(
    "aws_code", [bytes, unicode],
    u"The error response code.")
AWS_MESSAGE = Field.for_types(
    "aws_message", [unicode],
    u"A human-readable error message given by the response.",
)
AWS_REQUEST_ID = Field.for_types(
    "aws_request_id", [bytes, unicode],
    u"The unique identifier assigned by the server for this request.",
)

# Structures to help log ``boto.exception.EC2ResponseError`` from AWS.
BOTO_EC2RESPONSE_ERROR = MessageType(
    u"flocker:node:agents:blockdevice:aws:boto_ec2response_error",
    [AWS_CODE, AWS_MESSAGE, AWS_REQUEST_ID],
)

DEVICES = Field.for_types(
    u"devices", [list],
    u"List of devices currently in use by the compute instance.")
NO_AVAILABLE_DEVICE = MessageType(
    u"flocker:node:agents:blockdevice:aws:no_available_device",
    [DEVICES],
)
IN_USE_DEVICES = MessageType(
    u"flocker:node:agents:blockdevice:aws:in_use_devices",
    [DEVICES],
    u"Log current devices.",
)

NEW_DEVICES = Field.for_types(
    u"new_devices", [list],
    u"List of new devices in the compute instance.")
NEW_DEVICES_SIZE = Field.for_types(
    u"new_devices_size", [list],
    u"List of sizes of new devices in the compute instance.")
SIZE = Field.for_types(
    u"size", [int],
    u"Size, in bytes, of new device we are expecting to manifest."
    u"in the OS.")
TIME_LIMIT = Field.for_types(
    u"time_limit", [int],
    u"Time, in seconds, waited for new device to manifest in the OS.")
NO_NEW_DEVICE_IN_OS = MessageType(
    u"flocker:node:agents:blockdevice:aws:no_new_device",
    [NEW_DEVICES, NEW_DEVICES_SIZE, SIZE, TIME_LIMIT],
    u"No new block device manifested in the OS in given time.",)

VOLUME_ID = Field.for_types(
    u"volume_id", [bytes, unicode],
    u"The identifier of volume of interest.")
STATUS = Field.for_types(
    u"status", [bytes, unicode],
    u"Current status of the volume.")
TARGET_STATUS = Field.for_types(
    u"target_status", [bytes, unicode],
    u"Expected target status of the volume, as a result of an AWS API call.")
WAIT_TIME = Field.for_types(
    u"wait_time", [int],
    u"Time, in seconds, system waited for the volume to reach target status.")
WAITING_FOR_VOLUME_STATUS_CHANGE = MessageType(
    u"flocker:node:agents:blockdevice:aws:volume_status_change_wait",
    [VOLUME_ID, STATUS, TARGET_STATUS, WAIT_TIME],
    u"Waiting for a volume to reach target status.",)

BOTO_LOG_HEADER = u'flocker:node:agents:blockdevice:aws:boto_logs'
# End: Helper datastructures used by AWS storage driver.

# Begin: Helper datastructures used by OpenStack storage drivers

CODE = Field.for_types("code", [int], u"The HTTP response code.")
MESSAGE = Field.for_types(
    "message", [unicode],
    u"A human-readable error message given by the response.",
)
DETAILS = Field.for_types("details", [dict], u"Extra details about the error.")
REQUEST_ID = Field.for_types(
    "request_id", [bytes, unicode],
    u"The unique identifier assigned by the server for this request.",
)
URL = Field.for_types("url", [bytes, unicode], u"The request URL.")
METHOD = Field.for_types("method", [bytes, unicode], u"The request method.")

NOVA_CLIENT_EXCEPTION = MessageType(
    u"flocker:node:agents:blockdevice:openstack:nova_client_exception",
    [CODE, MESSAGE, DETAILS, REQUEST_ID, URL, METHOD],
)

RESPONSE = Field.for_types("response", [bytes, unicode], u"The response body.")

KEYSTONE_HTTP_ERROR = MessageType(
    u"flocker:node:agents:blockdevice:openstack:keystone_http_error",
    [CODE, RESPONSE, MESSAGE, DETAILS, REQUEST_ID, URL, METHOD],
)

LOCAL_IPS = Field(
    u"local_ips",
    repr,
    u"The IP addresses found on the target node."
)

API_IPS = Field(
    u"api_ips",
    repr,
    u"The IP addresses and instance_ids for all nodes."
)

COMPUTE_INSTANCE_ID_NOT_FOUND = MessageType(
    u"flocker:node:agents:blockdevice:openstack:compute_instance_id:not_found",
    [LOCAL_IPS, API_IPS],
    u"Unable to determine the instance ID of this node.",
)

CINDER_LOG_HEADER = u'flocker:node:agents:blockdevice:openstack'

# ActionType used by OpenStack storage driver.
OPENSTACK_ACTION = ActionType(
    CINDER_LOG_HEADER,
    [OPERATION],
    [],
    u"An IBlockDeviceAPI operation is executing using OpenStack"
    u"storage driver.")

CINDER_CREATE = u'flocker:node:agents:blockdevice:openstack:create_volume'
# End: Helper datastructures used by OpenStack storage driver.

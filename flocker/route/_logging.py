# Copyright ClusterHQ Inc.  See LICENSE file for details.

from eliot import Field, ActionType
from eliot._validation import ValidationError

from ipaddr import IPv4Address


def _system(name):
    return u"flocker:route:" + name


def validate_ipv4_address(value):
    if not isinstance(value, IPv4Address):
        raise ValidationError(
            value,
            u"Field %s requires type to be IPv4Address (not %s)" % (
                u"target_ip", type(value)))


def serialize_ipv4_address(address):
    return unicode(address)


TARGET_IP = Field(
    key=u"target_ip",
    serializer=serialize_ipv4_address,
    extraValidator=validate_ipv4_address,
    description=u"The IP address which is the target of a proxy.")


TARGET_PORT = Field.forTypes(
    u"target_port", [int],
    u"The port number which is the target of a proxy.")


ARGV = Field.forTypes(
    u"argv", [list],
    u"The argument list of a child process being executed.")


IPTABLES = ActionType(
    _system(u"iptables"),
    [ARGV],
    [],
    u"An iptables command which Flocker is executing against the system.")


CREATE_PROXY_TO = ActionType(
    _system(u"create_proxy_to"),
    [TARGET_IP, TARGET_PORT],
    [],
    U"Flocker is creating a new proxy.")


OPEN_PORT = ActionType(
    _system(u"open_port"),
    [TARGET_PORT],
    [],
    U"Flocker is opening a firewall port.")


DELETE_PROXY = ActionType(
    _system(u"delete_proxy"),
    [TARGET_IP, TARGET_PORT],
    [],
    u"Flocker is deleting an existing proxy.")


DELETE_OPEN_PORT = ActionType(
    _system(u"delete_open_port"),
    [TARGET_PORT],
    [],
    U"Flocker is close a firewall port.")

import os
import sys

import argparse
from subprocess import check_call
from twisted.python.filepath import FilePath
from textwrap import dedent
from pipes import quote as shell_quote

# Sources:
# http://docs.ceph.com/docs/master/start/quick-start-preflight/
# http://docs.ceph.com/docs/master/start/quick-ceph-deploy/

CEPH_RELEASE = 'infernalis'
KEYFILE = '/root/aws.pem'
OSD_PATH = "/var/local/osd"

parser = argparse.ArgumentParser(description='Install and configure Ceph.')


def aws_hostname(ip):
    # ec2-52-18-223-144
    return "ip-%s" % (ip.replace(".", "-"),)


def upload():
    """
    Upload the script to a control node and execute it in provisioning mode.

    The IP addresses of the control and agent nodes is taking from the
    acceptance testing environment variables:

        FLOCKER_ACCEPTANCE_CONTROL_NODE
        FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS"""

    SCRIPT_NAME = sys.argv[0]
    print SCRIPT_NAME


CEPH_DEPLOY_PATH = FilePath("/root/ceph-cluster")


def ceph_deploy(args):
    check_call(
        ["/opt/flocker/bin/ceph-deploy", "--username", "root"] + args,
        cwd=CEPH_DEPLOY_PATH.path)


def ssh(node, args):
    check_call([
        b"ssh",
        b"-oStrictHostKeyChecking=no",
        b"-o", b"PreferredAuthentications=publickey",
        b"-oControlMaster=no",
        b"-l", b"root",
        aws_hostname(node),
        ' '.join(map(shell_quote, args)),
    ])


def provision(monitor_node, nodes):
    """
    Provision Ceph onto ``nodes`` using ``monitor_node`` as a monitor node.
    """
    for node in nodes:
        # Populate known_hosts
        # and create ODS_PATH for later
        ssh(node, ["/bin/mkdir", "-p", OSD_PATH])
        ssh(node, ["firewall-cmd", "--zone=public",
                   "--add-port=6800-7300/tcp", "--permanent"])
        ssh(node, ["firewall-cmd", "--zone=public",
                   "--add-port=6800-7300/tcp"])

    ssh(monitor_node, ["firewall-cmd", "--zone=public",
                       "--add-port=6789/tcp", "--permanent"])
    ssh(monitor_node, ["firewall-cmd", "--zone=public",
                       "--add-port=6789/tcp"])

    os.mkdir("/root/ceph-cluster")
    ceph_deploy(["install"] + map(aws_hostname, nodes))

    for node in nodes:
        # Chown
        ssh(node, ["/bin/chown", "ceph:", OSD_PATH])

    ceph_deploy(["new", aws_hostname(monitor_node)])
    conf = CEPH_DEPLOY_PATH.child("ceph.conf")
    conf.setContent(
        conf.getContent() + dedent("""\
            osd_pool_default_size = 1
            osd_pool_default_min_size = 1
            """)
    )

    ceph_deploy(["mon", "create-initial"])

    osds = ["%s:%s" % (aws_hostname(ip), OSD_PATH) for ip in nodes]
    devs = ["%s:%s" % (aws_hostname(ip), OSD_PATH) for ip in nodes]
    ceph_deploy(["osd", "prepare"] + osds)
    ceph_deploy(["osd", "activate"] + devs)

    ceph_deploy(
        ["admin", aws_hostname(monitor_node)]
        + map(aws_hostname, nodes)
    )


if __name__ == "__main__":
    from sys import argv
    provision(argv[1], argv[2:])

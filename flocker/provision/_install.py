from fabric.api import run, execute, env

ZFS_REPO = ("https://s3.amazonaws.com/archive.zfsonlinux.org/"
            "fedora/zfs-release$(rpm -E %dist).noarch.rpm")
CLUSTERHQ_REPO = ("https://storage.googleapis.com/archive.clusterhq.com/"
                  "fedora/clusterhq-release$(rpm -E %dist).noarch.rpm")


def _task_install():
    run("yum install -y " + ZFS_REPO)
    run("yum install -y " + CLUSTERHQ_REPO)
    run("""
UNAME_R=$(uname -r)
PV=${UNAME_R%.*}
KV=${PV%%-*}
SV=${PV##*-}
ARCH=$(uname -m)
yum install -y https://kojipkgs.fedoraproject.org/packages/kernel/\
${KV}/${SV}/${ARCH}/kernel-devel-${UNAME_R}.rpm
""")
    run("yum install -y flocker-node")

    # Enable docker
    run("systemctl enable docker.service")
    run("systemctl start docker.service")

    # Disable firewall
    run('firewall-cmd --permanent --direct --add-rule ipv4 filter FORWARD 0 -j ACCEPT')  # noqa
    run('firewall-cmd --direct --add-rule ipv4 filter FORWARD 0 -j ACCEPT')

    # Creater flocker zfs pool
    run('mkdir /opt/flocker')
    run('truncate --size 1G /opt/flocker/pool-vdev')
    run('zpool create flocker /opt/flocker/pool-vdev')


def install(nodes, username):
    env.connection_attempts = 24
    env.timeout = 5
    env.pty = False
    execute(
        task=_task_install,
        hosts=["%s@%s" % (username, address) for address in nodes],
    )
    from fabric.network import disconnect_all
    disconnect_all()

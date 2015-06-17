=====================
Flocker Docker plugin
=====================

The Flocker Docker is the first Docker volumes plugin, connecting Docker directly to the Flocker volumes API.
It connects Flocker to Docker via the ``docker run -v name:path --volume-driver=flocker`` syntax.

See https://github.com/ClusterHQ/flocker-docker-plugin

Installing the Flocker Docker plugin
====================================

Since it's experimental, the Flocker Docker plugin does not yet come packaged for Ubuntu and CentOS.

Flocker itself currently supports Ubuntu 14.04 and CentOS 7.
So if you want to try the Flocker Docker plugin you'll need to be running Docker on one of these systems.

You'll also need to follow the Flocker installation instructions, either the (LINK) official instructions or (LINK) experimental installer.

You can easily install the flocker docker plugin using the following commands on each Docker node::

    sudo su -
    mkdir -p /opt
    cd /opt
    git clone https://github.com/clusterhq/flocker-docker-plugin
    cd flocker-docker-plugin
    python setup.py install

Now you'll need to set some variables which will be used later::

    FLOCKER_CONTROL_SERVICE_BASE_URL

Then if you are on Ubuntu 14.04, the following instructions will configure an upstart script to start the Flocker plugin before Docker::

    cat <<EOF > /etc/init/flocker-plugin.conf
    # flocker-plugin - flocker-plugin job file
    description "Flocker Plugin service"
    author "ClusterHQ <support@clusterhq.com>"
    respawn
    env FLOCKER_CONTROL_SERVICE_BASE_URL=${FLOCKER_CONTROL_SERVICE_BASE_URL}
    env MY_NETWORK_IDENTITY=${MY_NETWORK_IDENTITY}
    chdir /opt/flocker-docker-plugin
    exec twistd -noy powerstripflocker.tac
    EOF
    service flocker-plugin restart

If you are on a ``systemd`` system (e.g. CentOS 7), the following instructions will configure a ``systemd`` unit to start the Flocker plugin before Docker::

    cat <<EOF > /etc/systemd/system/flocker-plugin.service
    [Unit]
    Description=flocker-plugin - flocker-plugin job file
    [Service]
    Environment=FLOCKER_CONTROL_SERVICE_BASE_URL=${FLOCKER_CONTROL_SERVICE_BASE_URL}
    Environment=MY_NETWORK_IDENTITY=${MY_NETWORK_IDENTITY}
    ExecStart=/usr/bin/twistd -noy powerstripflocker.tac
    WorkingDirectory=/opty/flocker-docker-plugin
    [Install]
    WantedBy=multi-user.target
    EOF
    systemctl enable flocker-plugin.service
    systemctl start flocker-plugin.service

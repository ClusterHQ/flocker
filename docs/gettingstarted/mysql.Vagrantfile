# -*- mode: ruby -*-
# vi: set ft=ruby :

# This requires Vagrant 1.6.2 or newer (earlier versions can't reliably
# configure the Fedora 20 network stack).

# Vagrantfile API/syntax version. Don't touch unless you know what you're doing!
VAGRANTFILE_API_VERSION = "2"

ENV['VAGRANT_DEFAULT_PROVIDER'] = 'virtualbox'

$bootstrap = <<SCRIPT
set -e

# Make it possible to install flocker-node
mv clusterhq-flocker.repo /etc/yum.repos.d/

yum install -y flocker-node

# At the end of this bootstrap we'll (indirectly) ask Docker to write a very
# large file to its temporary directory.  /tmp is a small tmpfs mount which
# can't hold the file.  Convince Docker to write somewhere else instead.
echo "# Flocker-defined alternate temporary path to provide more temporary space." >> /etc/sysconfig/docker
echo "TMPDIR=/var/tmp" >> /etc/sysconfig/docker

systemctl enable docker
# Enabling Docker allows it to be started by socket activation, but it may
# already be running. Restart it to ensure that it picks up the new tmpdir
# configuration.
systemctl restart docker
systemctl enable geard
systemctl start geard

# Make it easy to authenticate as root
mkdir -p /root/.ssh
cp ~vagrant/.ssh/authorized_keys /root/.ssh

# Create a ZFS storage pool backed by a normal filesystem file.  This
# is a bad way to configure ZFS for production use but it is
# convenient for a demo in a VM.
mkdir -p /opt/flocker
truncate --size 1G /opt/flocker/pool-vdev
zpool create flocker /opt/flocker/pool-vdev
docker pull mysql:5.6.17
SCRIPT

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  config.vm.box = "clusterhq/flocker-dev"
  config.vm.provision :file, :source => "clusterhq-flocker.repo", :destination => "clusterhq-flocker.repo"
  config.vm.provision :shell, :inline => $bootstrap, :privileged => true

  config.vm.define "node1" do |node1|
    node1.vm.network :private_network, :ip => "172.16.255.250"
    node1.vm.hostname = "node1"
  end

  config.vm.define "node2" do |node2|
    node2.vm.network :private_network, :ip => "172.16.255.251"
    node2.vm.hostname = "node2"
  end

end

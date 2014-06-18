# -*- mode: ruby -*-
# vi: set ft=ruby :

# Vagrantfile API/syntax version. Don't touch unless you know what you're doing!
VAGRANTFILE_API_VERSION = "2"


$bootstrap = <<SCRIPT
# Remove this when the repository becomes public
cat <<EOF  >/etc/yum.repos.d/zfs-kmod.repo
[zfs-kmod]
name=Compiled ZFS modules
baseurl=http://data.hybridcluster.net/zfs-6.3-fedora20
gpgcheck=0
enabled=1
EOF

yum install -y zfs

systemctl enable docker
systemctl enable geard
SCRIPT

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  # All Vagrant configuration is done here. The most common configuration
  # options are documented and commented below. For a complete reference,
  # please see the online documentation at vagrantup.com.

  # Every Vagrant virtual environment requires a box to build off of.
  config.vm.box = "tomprince/flocker-dev"

  config.vm.provision :shell, :inline => $bootstrap, :privileged => true

  config.vm.define "node1" do |node1|
    node1.vm.network :private_network, :ip => "192.168.200.3"
  end
  #config.vm.define "node2" do |node2|
  #  node2.vm.network :private_network, :ip => "192.168.200.4"
  #end

  if Vagrant.has_plugin?("vagrant-cachier")
    config.cache.scope = :box
  end
end

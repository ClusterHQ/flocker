# -*- mode: ruby -*-
# vi: set ft=ruby :

# Vagrantfile API/syntax version. Don't touch unless you know what you're doing!
VAGRANTFILE_API_VERSION = "2"


$bootstrap = <<SCRIPT
set -e
yum install -y zfs

systemctl enable docker
systemctl start docker
systemctl enable geard
systemctl start geard
SCRIPT

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  config.vm.box = "tomprince/flocker-dev"

  config.vm.provision :shell, :inline => $bootstrap, :privileged => true

  if Vagrant.has_plugin?("vagrant-cachier")
    config.cache.scope = :box
  end
end

# -*- mode: ruby -*-
# vi: set ft=ruby :

# Vagrantfile API/syntax version. Don't touch unless you know what you're doing!
VAGRANTFILE_API_VERSION = "2"


$bootstrap = <<SCRIPT
set -e
yum install -y zfs
SCRIPT

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  config.ssh.forward_agent = true
  config.vm.box = "clusterhq/flocker-dev"
  config.vm.box_version = "> 0.0.0.880"

  config.vm.provision :shell, :inline => $bootstrap, :privileged => true

  if Vagrant.has_plugin?("vagrant-cachier")
    config.cache.scope = :box
  end
end

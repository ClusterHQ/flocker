# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.require_version ">= 1.6.2"

# Vagrantfile API/syntax version. Don't touch unless you know what you're doing!
VAGRANTFILE_API_VERSION = "2"

ENV['VAGRANT_DEFAULT_PROVIDER'] = 'virtualbox'

$bootstrap = <<SCRIPT
set -e
SCRIPT

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  config.vm.box = "clusterhq/flocker-dev"
  config.vm.box_version = "> 0.3.2.1714"

  # The following reduces the difference in network speed between the guest
  # and the host. See https://github.com/mitchellh/vagrant/issues/1807.
  config.vm.provider :virtualbox do |vb|
    vb.customize ["modifyvm", :id, "--natdnshostresolver1", "on"]
    vb.customize ["modifyvm", :id, "--natdnsproxy1", "on"]
  end

  config.vm.provision :shell, :inline => $bootstrap, :privileged => true
  # Use the git configuration from the host in the VM, if it is in the expected
  # location
  if File.exists?(File.join(Dir.home, ".gitconfig"))
    config.vm.provision "file", source: File.join(Dir.home, ".gitconfig"), destination: ".gitconfig"
  end

  if Vagrant.has_plugin?("vagrant-cachier")
    config.cache.scope = :box
  end
end

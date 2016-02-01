# -*- mode: ruby -*-
# vi: set ft=ruby :

# Virtual Machine for developing and releasing Flocker.
# After changing this file, refer to
# http://doc-dev.clusterhq.com/gettinginvolved/infrastructure/vagrant.html
# for information on how to publish a new version.

Vagrant.require_version ">= 1.6.2"

# Vagrantfile API/syntax version. Don't touch unless you know what you're doing!
VAGRANTFILE_API_VERSION = "2"

ENV['VAGRANT_DEFAULT_PROVIDER'] = 'virtualbox'

$bootstrap = <<SCRIPT
set -e
SCRIPT

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  config.vm.box = "clusterhq/flocker-dev"
  config.vm.box_url = "https://clusterhq-archive.s3.amazonaws.com/vagrant/flocker-dev.json"
  config.vm.box_version = "> 0.3.2.1714"

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

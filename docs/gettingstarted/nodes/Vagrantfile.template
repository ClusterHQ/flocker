# -*- mode: ruby -*-
# vi: set ft=ruby :

# This requires Vagrant 1.6.2 or newer (earlier versions can't reliably
# configure the Fedora 20 network stack).
Vagrant.require_version ">= 1.6.2"

# Vagrantfile API/syntax version. Don't touch unless you know what you're doing!
VAGRANTFILE_API_VERSION = "2"

ENV['VAGRANT_DEFAULT_PROVIDER'] = 'virtualbox'

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  config.vm.box = "clusterhq/flocker-tutorial"
  config.vm.box_version = "= 0.3.2.doc3"

  if Vagrant.has_plugin?("vagrant-cachier")
    config.cache.scope = :box
  end

  config.vm.define "node1" do |node1|
    node1.vm.network :private_network, :ip => "172.16.255.250"
    node1.vm.hostname = "node1"
  end

  config.vm.define "node2" do |node2|
    node2.vm.network :private_network, :ip => "172.16.255.251"
    node2.vm.hostname = "node2"
  end
end

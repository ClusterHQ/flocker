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

  config.vm.provision :shell, :inline => $bootstrap, :privileged => true
  # Use the git configuration from the host in the VM, if it is in the expected
  # location
  if File.exists?(File.join(Dir.home, ".gitconfig"))
    config.vm.provision "file", source: File.join(Dir.home, ".gitconfig"), destination: ".gitconfig"
  end

  config.vm.provision "shell", inline: "\
cd /vagrant && \
./admin/build-package --distribution centos-7 $(pwd) && \
VERSION=$(python -c \"import flocker, admin.release; print '-'.join(admin.release.make_rpm_version(flocker.__version__))\")
rpm -e clusterhq-flocker-node clusterhq-python-flocker && \
rpm -i clusterhq-python-flocker-${VERSION}.x86_64.rpm &&
rpm -i clusterhq-flocker-node-${VERSION}.x86_64.rpm &&
flocker --version
"

  if Vagrant.has_plugin?("vagrant-cachier")
    config.cache.scope = :box
  end
end

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

Kubernetes Setup Instructions

There are no packages for 1.5.0 or 1.5.1 yet.
 * https://github.com/kubernetes/kubernetes/issues/38707

So first install Kubernetes 1.4 packages for the systemd service files and then replace the binaries with the latest ones.

On all nodes:

.. code-block::
   # Follow standard kubeadm installation instrucitons
   # http://kubernetes.io/docs/getting-started-guides/kubeadm/
   curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add -
   cat <<EOF > /etc/apt/sources.list.d/kubernetes.list
   deb http://apt.kubernetes.io/ kubernetes-xenial main
   EOF
   apt-get update
   apt install kubelet kubeadm kubernetes-cni ebtables socat

   # Download latest kubernetes server binaries
   cd /opt
   wget https://dl.k8s.io/v1.5.1/kubernetes-server-linux-amd64.tar.gz
   tar xf kubernetes-server-linux-amd64.tar.gz

   # Download the beta release of kubeadm to replace the one included in the 1.5.1 binaries.
   cd kubernetes/server/bin
   rm kubeadm
   wget https://dl.k8s.io/ci-cross/v1.6.0-alpha.0.2074+a092d8e0f95f52/bin/linux/amd64/kubeadm
   chmod +x kubeadm

   # Replace the packaged binaries with symlinks to the latest binaries
   cd /usr/bin
   find /opt/kubernetes/server/bin/ -type f -executable | xargs -n1 ln -fs

Check the versions of all the components

.. code-block::
   root@acceptance-test-richardw-ddtbv7gt3qut4-0:/usr/bin# kubectl version
   Client Version: version.Info{Major:"1", Minor:"5", GitVersion:"v1.5.1", GitCommit:"82450d03cb057bab0950214ef122b67c83fb11df", GitTreeState:"clean", BuildDate:"2016-12-14T00:57:05Z", GoVersion:"go1.7.4", Compiler:"gc", Platform:"linux/amd64"}
   Server Version: version.Info{Major:"1", Minor:"5", GitVersion:"v1.5.1", GitCommit:"82450d03cb057bab0950214ef122b67c83fb11df", GitTreeState:"clean", BuildDate:"2016-12-14T00:52:01Z", GoVersion:"go1.7.4", Compiler:"gc", Platform:"linux/amd64"}

   root@acceptance-test-richardw-ddtbv7gt3qut4-0:/usr/bin# kubelet --version
   Kubernetes v1.5.1

   root@acceptance-test-richardw-ddtbv7gt3qut4-0:/usr/bin# kubeadm  version
   kubeadm version: version.Info{Major:"1", Minor:"6+", GitVersion:"v1.6.0-alpha.0.2074+a092d8e0f95f52", GitCommit:"a092d8e0f95f5200f7ae2cba45c75ab42da36537", GitTreeState:"clean", BuildDate:"2016-12-13T17:03:18Z", GoVersion:"go1.7.4", Compiler:"gc", Platform:"linux/amd64"}


Now continue with the kubeadm instructions:

On master node:

.. code-block::
   # Start a master
   kubeadm init

   # Make a note of the join command.
   # You'll need to run it on the other nodes later. E.g
   # kubeadm join --token=860565.02b8ce8cfcc713cb 10.240.0.7

   # Allow master to host pods
   kubectl taint nodes --all dedicated-

   # Install networking
   # https://github.com/weaveworks/weave-kube
   kubectl apply -f https://git.io/weave-kube

   # Wait for kube-dns to be running
   kubectl get pods --all-namespaces

   # Examine its state
   kubectl --namespace kube-system describe pod kube-dns-2924299975-rplps


On the other nodes:

.. code-block::

   # Join the master using the token line from previous step
   kubeadm join --token=860565.02b8ce8cfcc713cb 10.240.0.7

Back on the master, check that the node has joined

.. code-block::

   root@acceptance-test-richardw-ddtbv7gt3qut4-0:~# kubectl get nodes
   NAME                                       STATUS         AGE
   acceptance-test-richardw-ddtbv7gt3qut4-0   Ready,master   7m
   acceptance-test-richardw-w63eekhmjhbhu-0   Ready          16s

Install a sample application to test the cluster:

.. code-block::

   # Install the sock-shop application
   kubectl create namespace sock-shop
   kubectl apply -n sock-shop -f "https://github.com/microservices-demo/microservices-demo/blob/master/deploy/kubernetes/complete-demo.yaml?raw=true"


   # Wait for it to start by monitoring the pod status in the sock-shop namespace.
   kubectl get pods --namespace sock-shop

   # Find the IP and port and check you can connect to the web ui
   kubectl describe svc front-end -n sock-shop

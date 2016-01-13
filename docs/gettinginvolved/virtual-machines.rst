.. _building-flocker-virtual-machine-images:

Building Flocker Virtual Machine Images
=======================================

Flocker virtual machine images can be built using a tool called Packer.
The Flocker source repository has an ``admin/packer`` sub-directory which contains Packer templates and provisioning scripts.
These are used to create Ubuntu AMI images for use in the Flocker Cloudformation demonstration environment.
The images are built in two steps: Ubuntu + Docker base image then Flocker the image.
This speeds up the build process because Docker does not have to be installed each time we update the Flocker image.
It also allows control over the version of Docker in our demonstration environment.
i.e we only need to upgrade when a new version of Docker is released and when it is supported by Flocker.

Follow these steps to build the virtual machine images:

1. Install Packer.

   See https://www.packer.io/ for complete instructions.

2. Build the Ubuntu-14.04 + Docker base image.


   .. prompt:: bash #

      /opt/packer/packer build \
          admin/packer/template_ubuntu-14.04_docker.json

   Packer will copy the new image to all available AWS regions.
   The image will have a unique name in each region.
   Packer will print the region specific AMI image names.
   The images are built in the ``us-west-1`` region.
   Make a note of the ``us-west-1`` AMI image name because you'll use it for building the Flocker AMI in the next step.

3. Build the Flocker image.

   This image is based on the ``us-west-1`` image generated in the previous step.
   Substitute the name of the ``us-west-1`` image in the following command line.

   .. prompt:: bash #

      /opt/packer/packer build \
          -var "flocker_branch=master" \
          -var "source_ami=<name of AMI image from previous step>" \
          admin/packer/template_ubuntu-14.04_flocker.json

Choosing a Base Image
---------------------

The Ubuntu-14.04 base AMI images are updated frequently.
The names of the latest images can be found at:

* https://cloud-images.ubuntu.com/locator/ec2/

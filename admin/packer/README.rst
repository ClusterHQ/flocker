Building Flocker Demo Images Using Packer

The templates and provisioning scripts in this directory are used to create Ubuntu AMI images for use in the Flocker Cloudformation demo environment.

Usage:

* Install Packer

  https://www.packer.io/

* Build Ubuntu-14.04 + Docker base image

  ```
  /opt/packer/packer build \
      -machine-readable \
      admin/packer/template_ubuntu-14.04_docker.json
  ```

* Build Ubuntu-14.04 + Docker + Flocker on top of the image generated in the previous step.

  ```
  /opt/packer/packer build \
      -machine-readable \
      -var "flocker_branch=master" \
      -var "source_ami=ami-0a254f6a" \
      admin/packer/template_ubuntu-14.04_flocker.json
  ```

# Copyright ClusterHQ Inc. See LICENSE file for details.
#
# A Docker image for building RPMs in a clean CentOS 7 build environment.
#

FROM clusterhqci/fpm-centos-7
MAINTAINER ClusterHQ <contact@clusterhq.com>
COPY requirements/*.txt /requirements/
RUN ["pip", "install", "--upgrade", "pip==8.1.2", "setuptools==23.0.0"]
RUN ["pip", "install",\
     "--requirement", "/requirements/all.txt",\
     "--constraint", "/requirements/constraints.txt"]
VOLUME /flocker
WORKDIR /
ENTRYPOINT ["/flocker/admin/build-package-entrypoint", "--destination-path=/output"]

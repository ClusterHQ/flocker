# Copyright ClusterHQ Inc. See LICENSE file for details.
#
# A Docker image for building packages in a clean Ubuntu 15.10 build
# environment.
#

FROM clusterhqci/fpm-ubuntu-wily
MAINTAINER ClusterHQ <contact@clusterhq.com>
COPY requirements.txt /tmp/
RUN ["pip", "install", "-r", "/tmp/requirements.txt"]
VOLUME /flocker
ENTRYPOINT ["/flocker/admin/build-package-entrypoint", "--destination-path=/output"]

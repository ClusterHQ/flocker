# Copyright Hybrid Logic Ltd. See LICENSE file for details.
#
# A Docker image for building packages in a clean Ubuntu 15.04 build
# environment.
#

FROM clusterhqci/fpm-ubuntu-vivid
MAINTAINER ClusterHQ <contact@clusterhq.com>
COPY requirements.txt /tmp/
RUN ["pip", "install", "-r", "/tmp/requirements.txt"]
VOLUME /flocker
ENTRYPOINT ["/flocker/admin/build-package-entrypoint", "--destination-path=/output"]

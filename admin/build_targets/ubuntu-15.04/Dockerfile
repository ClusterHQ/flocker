# Copyright Hybrid Logic Ltd. See LICENSE file for details.
#
# A Docker image for building packages in a clean Ubuntu 15.04 build
# environment.
#

FROM ubuntu:15.04
MAINTAINER ClusterHQ <contact@clusterhq.com>
RUN ["apt-get", "update"]
RUN ["apt-get", "install", "--no-install-recommends", "-y", "git", "ruby-dev", "libffi-dev", "libssl-dev", "build-essential", "python-pip", "python2.7-dev", "lintian"]
# Despite being a packaging tool, fpm isn't yet packaged for Ubuntu
# See https://github.com/jordansissel/fpm/issues/611 and
# https://github.com/jordansissel/fpm/issues/657
RUN ["gem", "install", "fpm"]
COPY requirements.txt /tmp/
RUN ["pip", "install", "-r", "/tmp/requirements.txt"]
VOLUME /flocker
ENTRYPOINT ["/flocker/admin/build-package-entrypoint", "--destination-path=/output"]

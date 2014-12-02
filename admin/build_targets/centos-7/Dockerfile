# Copyright Hybrid Logic Ltd. See LICENSE file for details.
#
# A Docker image for building RPMs in a clean Centos 7 build environment.
#

FROM centos:centos7
MAINTAINER ClusterHQ <contact@clusterhq.com>
RUN ["yum", "groupinstall", "--assumeyes", "Development Tools"]
RUN ["yum", "install", "--assumeyes", "git", "ruby-devel", "python-devel"]
# Despite being a packaging tool, fpm isn't yet packaged for Fedora.
# See https://github.com/jordansissel/fpm/issues/611
RUN ["gem", "install", "fpm"]
WORKDIR /tmp
RUN ["curl", "--output", "get-pip.py", "https://raw.githubusercontent.com/pypa/pip/master/contrib/get-pip.py"]
RUN ["python", "get-pip.py"]
# The Centos7 packaged virtualenv --relocatable seems to remove the `flocker-*` scripts.
# Install it from PyPI instead.
RUN ["pip", "install", "twisted", "characteristic", "virtualenv"]
VOLUME /flocker
WORKDIR /
ENTRYPOINT ["/flocker/admin/build-package-entrypoint", "--destination-path=/output"]

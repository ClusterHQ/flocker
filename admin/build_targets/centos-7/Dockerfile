# Copyright Hybrid Logic Ltd. See LICENSE file for details.
#
# A Docker image for building RPMs in a clean CentOS 7 build environment.
#

FROM centos:centos7
MAINTAINER ClusterHQ <contact@clusterhq.com>
# URLGRABBER_DEBUG=1 to log low-level network info - see FLOC-2640
RUN ["env", "URLGRABBER_DEBUG=1", "yum", "groupinstall", "--assumeyes", "Development Tools"]
RUN ["env", "URLGRABBER_DEBUG=1", "yum", "install", "--assumeyes", "epel-release"]
RUN ["env", "URLGRABBER_DEBUG=1", "yum", "install", "--assumeyes", "git", "ruby-devel", "python-devel", "libffi-devel", "openssl-devel", "python-pip", "rpmlint"]
# Despite being a packaging tool, fpm isn't yet packaged for CentOS.
# See https://github.com/jordansissel/fpm/issues/611
RUN ["gem", "install", "fpm"]
COPY requirements.txt /tmp/
RUN ["pip", "install", "-r", "/tmp/requirements.txt"]
VOLUME /flocker
WORKDIR /
ENTRYPOINT ["/flocker/admin/build-package-entrypoint", "--destination-path=/output"]

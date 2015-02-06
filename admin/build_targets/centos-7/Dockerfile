# Copyright Hybrid Logic Ltd. See LICENSE file for details.
#
# A Docker image for building RPMs in a clean CentOS 7 build environment.
#

FROM centos:centos7
MAINTAINER ClusterHQ <contact@clusterhq.com>
RUN ["yum", "groupinstall", "--assumeyes", "Development Tools"]
RUN ["yum", "install", "--assumeyes", "epel-release"]
RUN ["yum", "install", "--assumeyes", "git", "ruby-devel", "python-devel", "python-pip", "rpmlint"]
# Despite being a packaging tool, fpm isn't yet packaged for Fedora.
# See https://github.com/jordansissel/fpm/issues/611
RUN ["gem", "install", "fpm"]

RUN ["pip", "install", "twisted==14.0.2", "characteristic==14.1.0", "virtualenv==12.0.5", "effect=0.1a13"]
VOLUME /flocker
WORKDIR /
ENTRYPOINT ["/flocker/admin/build-package-entrypoint", "--destination-path=/output"]

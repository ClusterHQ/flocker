# Copyright Hybrid Logic Ltd. See LICENSE file for details.
#
# A Docker image for building RPMs in a clean Fedora 20 build environment.
#

FROM fedora:20
MAINTAINER ClusterHQ <contact@clusterhq.com>
RUN ["yum", "install", "--assumeyes", "@buildsys-build", "git", "ruby-devel", "libffi-devel", "openssl-devel", "python-devel", "python-pip", "rpmlint"]
# Despite being a packaging tool, fpm isn't yet packaged for Fedora.
# See https://github.com/jordansissel/fpm/issues/611
RUN ["gem", "install", "fpm"]
COPY requirements.txt /tmp/
RUN ["pip", "install", "-r", "/tmp/requirements.txt"]
VOLUME /flocker
ENTRYPOINT ["/flocker/admin/build-package-entrypoint", "--destination-path=/output"]

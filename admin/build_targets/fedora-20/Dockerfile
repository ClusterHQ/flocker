# Copyright Hybrid Logic Ltd. See LICENSE file for details.
#
# A Docker image for building RPMs in a clean Fedora 20 build environment.
#

FROM fedora:20
MAINTAINER ClusterHQ <contact@clusterhq.com>
RUN ["yum", "install", "--assumeyes", "@buildsys-build", "git", "ruby-devel", "python-devel", "python-pip", "rpmlint"]
# Despite being a packaging tool, fpm isn't yet packaged for Fedora.
# See https://github.com/jordansissel/fpm/issues/611
RUN ["gem", "install", "fpm"]

RUN ["pip", "install", "twisted==15.0.0", "characteristic==14.1.0", "virtualenv==12.0.5", "effect==0.1a13" , "boto==2.30.0"]
VOLUME /flocker
ENTRYPOINT ["/flocker/admin/build-package-entrypoint", "--destination-path=/output"]

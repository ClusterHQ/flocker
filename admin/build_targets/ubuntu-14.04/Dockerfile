# Copyright Hybrid Logic Ltd. See LICENSE file for details.
#
# A Docker image for building packages in a clean Ubuntu 14.04 build
# environment.
#

FROM ubuntu:14.04
MAINTAINER Richard Wall <richard.wall@clusterhq.com>
RUN ["apt-get", "update"]
RUN ["apt-get", "install", "--no-install-recommends", "-y", "git", "ruby-dev", "build-essential", "python-twisted", "python-pip", "python-virtualenv", "python2.7-dev"]
# XXX: Characteristic isn't packaged for Ubuntu.
RUN ["pip", "install", "characteristic"]
# Despite being a packaging tool, fpm isn't yet packaged for Ubuntu
# See https://github.com/jordansissel/fpm/issues/611 and
# https://github.com/jordansissel/fpm/issues/657
RUN ["gem", "install", "fpm"]
VOLUME /flocker
ENTRYPOINT ["/flocker/admin/build-package-entrypoint", "--destination-path=/output"]

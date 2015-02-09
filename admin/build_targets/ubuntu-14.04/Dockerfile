# Copyright Hybrid Logic Ltd. See LICENSE file for details.
#
# A Docker image for building packages in a clean Ubuntu 14.04 build
# environment.
#

FROM ubuntu:14.04
MAINTAINER ClusterHQ <contact@clusterhq.com>
RUN ["apt-get", "update"]
RUN ["apt-get", "install", "--no-install-recommends", "-y", "git", "ruby-dev", "build-essential", "python-pip", "python2.7-dev", "lintian"]
# Despite being a packaging tool, fpm isn't yet packaged for Ubuntu
# See https://github.com/jordansissel/fpm/issues/611 and
# https://github.com/jordansissel/fpm/issues/657
RUN ["gem", "install", "fpm"]

RUN ["pip", "install", "twisted==15.0.0", "characteristic==14.1.0", "virtualenv==12.0.5", "effect==0.1a13" , "boto==2.30.0"]
VOLUME /flocker
ENTRYPOINT ["/flocker/admin/build-package-entrypoint", "--destination-path=/output"]

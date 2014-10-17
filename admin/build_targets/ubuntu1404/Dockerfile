# Copyright Hybrid Logic Ltd. See LICENSE file for details.
#
# A Docker image for running the ``admin/build-package`` script in a clean
# Ubuntu 14.04 build environment.
#
# Build:
# docker build --tag='clusterhq/build_ubuntu:14.04' ~/projects/flocker/admin/build_targets/ubuntu1404
#
# Run:
# docker run --volume=~/projects/flocker:/flocker clusterhq/build_ubuntu:14.04 https://storage.googleapis.com/archive.clusterhq.com/downloads/flocker/Flocker-0.2.1-py2-none-any.whl

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
ENTRYPOINT ["/flocker/admin/build-package", "--destination-path=/flocker"]

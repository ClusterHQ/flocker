# Copyright Hybrid Logic Ltd. See LICENSE file for details.
#
# A Docker image for running Flocker tests via ``tox`` in a clean
# Ubuntu 14.04 environment.
#
# Build:
# docker build --tag='clusterhq/test_ubuntu:14.04' ~/projects/flocker/admin/test_targets/ubuntu1404
#
# Run:
# docker run --volume=~/projects/flocker:/flocker clusterhq/test_ubuntu:14.04 -e admin

FROM ubuntu:14.04
MAINTAINER Richard Wall <richard.wall@clusterhq.com>
RUN ["apt-get", "update"]
RUN ["apt-get", "install", "--no-install-recommends", "-y", "build-essential", "git", "python-tox"]
RUN ["apt-get", "install", "--no-install-recommends", "-y", "python-dev"]
RUN ["apt-get", "install", "--no-install-recommends", "-y", "ruby-dev"]
# Despite being a packaging tool, fpm isn't yet packaged for Ubuntu
# See https://github.com/jordansissel/fpm/issues/611 and
# https://github.com/jordansissel/fpm/issues/657
RUN ["gem", "install", "fpm"]
VOLUME /flocker
WORKDIR /flocker
ENTRYPOINT ["tox"]

# Copyright Hybrid Logic Ltd. See LICENSE file for details.
#
# A Docker image for running Flocker tests via ``tox`` in a clean
# Fedora 20 environment.
#
# Build:
# docker build --tag='clusterhq/test_fedora:20' ~/projects/flocker/admin/test_targets/fedora20
#
# Run:
# docker run --volume=~/projects/flocker:/flocker clusterhq/test_fedora:20 -e admin

FROM mattdm/fedora-small:f20
MAINTAINER Richard Wall <richard.wall@clusterhq.com>
RUN ["yum", "install", "--assumeyes", "@buildsys-build", "git", "python-tox", "python-dev", "ruby-devel", "libffi-devel", "openssl-devel", "rpmlint"]
# Despite being a packaging tool, fpm isn't yet packaged for Fedora.
# See https://github.com/jordansissel/fpm/issues/611
RUN ["gem", "install", "fpm"]
VOLUME /flocker
WORKDIR /flocker
ENTRYPOINT ["tox"]

# Copyright Hybrid Logic Ltd. See LICENSE file for details.
#
# A Docker image for running Flocker tests via ``tox`` in a clean
# Centos7 environment.
#
# Build:
# docker build --tag='clusterhq/test_centos:7' ~/projects/flocker/admin/test_targets/centos7
#
# Run:
# docker run --volume=~/projects/flocker:/flocker clusterhq/test_centos:7 -e admin

FROM centos
MAINTAINER Richard Wall <richard.wall@clusterhq.com>
RUN ["yum", "groupinstall", "--assumeyes", "Development Tools"]
RUN ["yum", "install", "--assumeyes", "git", "python-devel", "ruby-devel", "libffi-devel", "openssl-devel", "rpmlint"]
# Despite being a packaging tool, fpm isn't yet packaged for Centos.
# See https://github.com/jordansissel/fpm/issues/611
RUN ["gem", "install", "fpm"]
WORKDIR /tmp
RUN ["curl", "--output", "get-pip.py", "https://raw.githubusercontent.com/pypa/pip/master/contrib/get-pip.py"]
RUN ["python", "get-pip.py"]
RUN ["pip", "install", "tox"]
VOLUME /flocker
WORKDIR /flocker
ENTRYPOINT ["tox"]

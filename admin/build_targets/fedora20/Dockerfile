# Copyright Hybrid Logic Ltd. See LICENSE file for details.
#
# A Docker image for running the ``admin/build-package`` script in a clean
# Fedora 20 build environment.
#
# Build:
# docker build --tag='clusterhq/build_fedora:20' ~/projects/flocker/admin/build_targets/fedora20
#
# Run:
# docker run --volume=~/projects/flocker:/flocker clusterhq/build_fedora:20 https://storage.googleapis.com/archive.clusterhq.com/downloads/flocker/Flocker-0.2.1-py2-none-any.whl
#
# TODO: Explicitly uninstall prelink (if it's installed). See
# https://github.com/jordansissel/fpm/issues/352

FROM mattdm/fedora-small:f20
MAINTAINER Richard Wall <richard.wall@clusterhq.com>
RUN ["curl", "--output", "/etc/yum.repos.d/hybridlogic.repo", "https://copr.fedoraproject.org/coprs/tomprince/hybridlogic/repo/fedora-20-x86_64/tomprince-hybridlogic-fedora-20-x86_64.repo"]
RUN ["yum", "install", "--assumeyes", "@buildsys-build", "git", "python-twisted", "python-characteristic", "python-virtualenv", "ruby-devel"]
# Despite being a packaging tool, fpm isn't yet packaged for Fedora.
# See https://github.com/jordansissel/fpm/issues/611
RUN ["gem", "install", "fpm"]
VOLUME /flocker
ENTRYPOINT ["/flocker/admin/build-package", "--destination-path=/flocker"]

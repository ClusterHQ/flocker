# Copyright Hybrid Logic Ltd. See LICENSE file for details.
#
# A Docker image for building RPMs in a clean Fedora 20 build environment.
#

FROM fedora:20
MAINTAINER ClusterHQ <contact@clusterhq.com>
RUN ["curl", "--output", "/etc/yum.repos.d/hybridlogic.repo", "https://copr.fedoraproject.org/coprs/tomprince/hybridlogic/repo/fedora-20-x86_64/tomprince-hybridlogic-fedora-20-x86_64.repo"]
RUN ["yum", "install", "--assumeyes", "@buildsys-build", "git", "python-twisted", "python-characteristic", "python-virtualenv", "ruby-devel"]
# Despite being a packaging tool, fpm isn't yet packaged for Fedora.
# See https://github.com/jordansissel/fpm/issues/611
RUN ["gem", "install", "fpm"]
VOLUME /flocker
ENTRYPOINT ["/flocker/admin/build-package-entrypoint", "--destination-path=/output"]

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

RUN ["pip", "install", "Twisted==15.1.0", "characteristic==14.1.0", "pyOpenSSL==0.14", "pycrypto==2.6.1", "virtualenv==12.0.5", "effect==0.1a13" , "boto==2.30.0", "requests==2.4.3", "requests-file==1.0", "ipaddr==2.1.11", "eliot==0.6.0", "pyrsistent==0.9.1"]
VOLUME /flocker
ENTRYPOINT ["/flocker/admin/build-package-entrypoint", "--destination-path=/output"]

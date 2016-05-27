# Copyright ClusterHQ Inc. See LICENSE file for details.
#
# A Docker image for updating Flocker pinned requirements.
#
# This Dockerfile will be built by a script which will have constructed a
# temporary directory containing a copy of Flocker/requirements and the
# entrypoint script.

FROM quay.io/pypa/manylinux1_x86_64:latest
MAINTAINER ClusterHQ <contact@clusterhq.com>
COPY entrypoint /entrypoint
RUN ["chmod", "+x", "/entrypoint"]
# Some packages for compiling CFFI and cryptography
RUN ["yum", "install", "-y", "libffi-devel", "openssl-devel"]
RUN ["/opt/python/cp27-cp27m/bin/pip", "install", "pip==8.1.2"]
COPY requirements/*.txt /requirements/
RUN ["/opt/python/cp27-cp27m/bin/pip", "download",\
     "--dest", "/downloads",\
     "--constraint", "/requirements/constraints.txt",\
     "--requirement", "/requirements/all.txt"]
ENTRYPOINT ["/entrypoint"]

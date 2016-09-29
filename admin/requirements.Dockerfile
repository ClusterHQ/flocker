# Copyright ClusterHQ Inc. See LICENSE file for details.
#
# A Docker image for updating Flocker pinned requirements.
#
# This Dockerfile will be built by a script which will have constructed a
# temporary directory containing a copy of Flocker/requirements and the
# entrypoint script.

FROM alpine:latest
MAINTAINER ClusterHQ <contact@clusterhq.com>
RUN apk add --update alpine-sdk py-pip git python-dev openssl-dev linux-headers libffi-dev enchant-dev
COPY entrypoint /entrypoint
RUN ["chmod", "+x", "/entrypoint"]
# Some packages for compiling CFFI and cryptography
RUN ["/usr/bin/pip", "install", "--upgrade", "pip==8.1.2"]
RUN ["/usr/bin/pip", "install", "wheel"]
COPY requirements /requirements
RUN ["/usr/bin/pip", "wheel",\
     "--wheel-dir", "/wheelhouse",\
     "--constraint", "/requirements/constraints.txt",\
     "--requirement", "/requirements/all.txt.latest"]
RUN ["/usr/bin/pip", "wheel",\
     "--wheel-dir", "/wheelhouse",\
     "--constraint", "/requirements/constraints.txt",\
     "--requirement", "/requirements/all.txt.latest"]
ENTRYPOINT ["/entrypoint"]

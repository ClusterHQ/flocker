# Copyright ClusterHQ Inc. See LICENSE file for details.
#
# A Docker image for building packages in a clean Ubuntu 15.10 build
# environment.
#

FROM clusterhqci/fpm-ubuntu-wily
MAINTAINER ClusterHQ <contact@clusterhq.com>
COPY requirements/*.txt /requirements/
RUN ["pip", "install", "--upgrade", "pip==8.1.2", "setuptools==22.0.5"]
RUN ["pip", "install",\
     "--requirement", "/requirements/all.txt",\
     "--constraint", "/requirements/constraints.txt"]
VOLUME /flocker
ENTRYPOINT ["/flocker/admin/build-package-entrypoint", "--destination-path=/output"]

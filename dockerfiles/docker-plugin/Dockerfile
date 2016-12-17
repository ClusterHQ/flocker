FROM ubuntu:16.04

MAINTAINER ClusterHQ <contact@clusterhq.com>

RUN \
    apt-get --yes update \
    && apt-get --yes install --no-install-recommends \
        apt-transport-https \
        ca-certificates \
    && apt-get --yes clean

ARG FLOCKER_VERSION="*"
ARG FLOCKER_REPOSITORY="https://clusterhq-archive.s3.amazonaws.com/ubuntu/16.04/amd64"
RUN echo "deb ${FLOCKER_REPOSITORY} /" > /etc/apt/sources.list.d/clusterhq.list
RUN \
    apt-get --yes update \
    && apt-get --yes install --no-install-recommends --allow-unauthenticated \
        clusterhq-python-flocker=${FLOCKER_VERSION} \
        clusterhq-flocker-node=${FLOCKER_VERSION}

VOLUME /etc/flocker

ENTRYPOINT ["/opt/flocker/bin/flocker-docker-plugin", "--agent-config=/etc/flocker/agent.yml"]

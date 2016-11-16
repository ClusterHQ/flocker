FROM ubuntu:16.04

MAINTAINER ClusterHQ <contact@clusterhq.com>

ENV FLOCKER_VERSION 1.14.0-1

RUN \
	apt-get update \
	&& apt-get install -y \
		apt-transport-https \
		software-properties-common \ 
	&& add-apt-repository -y \
		"deb https://clusterhq-archive.s3.amazonaws.com/ubuntu/$(lsb_release --release --short)/\$(ARCH) /" \
	&& apt-get update \
	&& apt-get install -y --allow-unauthenticated \
		clusterhq-python-flocker=${FLOCKER_VERSION} \
      		clusterhq-flocker-node=${FLOCKER_VERSION} \
	&& apt-get clean

RUN find / -name flocker-dataset-agent

RUN ls -l /opt/flocker/bin/flocker-dataset-agent
RUN ls -l /usr/sbin/flocker-dataset-agent

ENTRYPOINT ["/usr/sbin/flocker-dataset-agent"]

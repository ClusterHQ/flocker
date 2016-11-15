FROM ubuntu:14.04
MAINTAINER Madhuri Yechuri <madhuri.yechuri@clusterhq.com>

# Note: apt-get install requires the `-1` (epoch) suffix.
ENV FLOCKER_VERSION 1.14.0-1

RUN sudo apt-get update
RUN sudo apt-get -y install apt-transport-https software-properties-common
RUN sudo add-apt-repository -y ppa:james-page/docker
RUN sudo add-apt-repository -y "deb https://clusterhq-archive.s3.amazonaws.com/ubuntu/$(lsb_release --release --short)/\$(ARCH) /"

RUN sudo apt-get update && sudo apt-get -y --force-yes install \
      clusterhq-python-flocker=${FLOCKER_VERSION} \
      clusterhq-flocker-node=${FLOCKER_VERSION}



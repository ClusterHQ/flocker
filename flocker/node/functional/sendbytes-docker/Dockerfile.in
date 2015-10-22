FROM busybox
MAINTAINER ClusterHQ <support@clusterhq.com>
ADD . /
# If installed via wheel, the installed file will not have +x set.
RUN ["chmod", "+x", "/run.sh"]
CMD ["/bin/sh",  "-e", "run.sh", "{host}", "{port}", "{bytes}", "{timeout}"]

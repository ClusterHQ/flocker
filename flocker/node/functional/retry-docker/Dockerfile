# Docker image that keeps a count of the number of times it has been run
# in /data/count.
FROM python:2.7-slim
VOLUME /data
ADD run /usr/local/bin/run
WORKDIR /data
CMD ["/usr/local/bin/run"]

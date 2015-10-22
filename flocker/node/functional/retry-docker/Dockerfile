# Docker image that keeps a count of the number of times it has been run
# in /data/count.
FROM python:2.7-slim
VOLUME /data
WORKDIR /data

ADD run /usr/local/bin/run
# If installed via wheel, the installed file will not have +x set.
RUN ["chmod", "+x", "/usr/local/bin/run"]

CMD ["/usr/local/bin/run"]

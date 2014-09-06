# Docker image that prints out the provided environment and then
# loops forever.
FROM busybox
CMD ["/bin/sh",  "-c", "env > /data/env && while :; do :; done"]

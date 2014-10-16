FROM mattdm/fedora-small:f20
MAINTAINER Richard Wall <richard.wall@clusterhq.com>
RUN ["yum", "install", "-y", "python-virtualenv", "python-twisted"]
VOLUME /flocker
CMD ["/flocker/admin/build-package", "--destination-path=/", "/flocker"]

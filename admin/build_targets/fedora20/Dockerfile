FROM mattdm/fedora-small:f20
MAINTAINER Richard Wall <richard.wall@clusterhq.com>
RUN ["curl", "--output", "/etc/yum.repos.d/hybridlogic.repo", "https://copr.fedoraproject.org/coprs/tomprince/hybridlogic/repo/fedora-20-x86_64/tomprince-hybridlogic-fedora-20-x86_64.repo"]
RUN ["yum", "install", "--assumeyes", "@buildsys-build", "git", "python-twisted", "python-characteristic", "python-virtualenv", "ruby-devel"]
RUN ["gem", "install", "fpm"]
VOLUME /flocker
ENTRYPOINT ["/flocker/admin/build-package", "--destination-path=/flocker"]

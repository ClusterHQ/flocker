FROM quay.io/pypa/manylinux1_x86_64:latest
RUN ["yum", "install", "-y", "libffi-devel", "openssl-devel"]
RUN ["/opt/python/cp27-cp27m/bin/pip", "install", "pip==8.1.2"]
ADD *.txt /tmp/requirements/
RUN ["/opt/python/cp27-cp27m/bin/pip", "download", "--dest", "/tmp/downloads", "--requirement", "/tmp/requirements/all.txt"]
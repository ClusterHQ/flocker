#!/bin/sh

# Cleanup image so that it compresses better
rm -rf /tmp/* /var/tmp/*
# Zero out all the free space on the disk
dd if=/dev/zero of=/EMPTY bs=1M || true
rm -f /EMPTY

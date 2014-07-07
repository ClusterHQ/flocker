#!/bin/sh

# Cleanup image so that it compresses better
rm -rf /tmp/* /var/tmp/*
dd if=/dev/zero of=/EMPTY bs=1M || true
rm -f /EMPTY

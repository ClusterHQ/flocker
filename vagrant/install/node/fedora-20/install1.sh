#!/bin/sh

set -e -x

sudo yum upgrade -y kernel
sudo grubby --set-default-index 0

#!/bin/sh
set -e 

while true; do
    if echo "xxx" | nc "127.0.0.1" "31337"; then
        break
    fi
done

#!/bin/bash
# Generate certs for {Docker, Swarm} TLS.
set -ex

: ${s3_bucket:?}

rm -rf /tmp/swarm-tls-config
mkdir -p /tmp/swarm-tls-config
cd /tmp/swarm-tls-config

# Get expect to autofill openssl inputs
sudo apt-get install -y expect

# Generate CA private and public keys
echo > /tmp/swarm-tls-config/createca.exp << EOF
#!/usr/bin/expect -f
set timeout -1
spawn openssl genrsa -passout stdin -aes256 -out ca-key.pem 4096
match_max 100000
send -- "welcome\r"
expect eof
EOF
/tmp/swarm-tls-config/createca.exp

# Create server key and CSR.
openssl genrsa -out server-key.pem 4096

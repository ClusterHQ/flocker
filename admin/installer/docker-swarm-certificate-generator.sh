#!/bin/bash
# Generate certs for {Docker, Swarm} TLS.
set -ex

: ${s3_bucket:?}

rm -rf /tmp/docker-swarm-tls-config
mkdir -p /tmp/docker-swarm-tls-config
cd /tmp/docker-swarm-tls-config

# Get expect to autofill openssl inputs
sudo apt-get install -y expect

PASSPHRASE=$(dd bs=18 count=1 if=/dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | fold -w 32 | head -n 1)

# Generate CA private and public keys
cat > /tmp/docker-swarm-tls-config/createca1.exp << EOF
#!/usr/bin/expect -f
set timeout -1
spawn openssl genrsa -passout stdin -aes256 -out ca-key.pem 4096
match_max 100000
send -- "${PASSPHRASE}\r"
expect eof
EOF
chmod +x /tmp/docker-swarm-tls-config/createca1.exp
/tmp/docker-swarm-tls-config/createca1.exp

cat > /tmp/docker-swarm-tls-config/createca2.exp << EOF
#!/usr/bin/expect -f
set timeout -1
spawn openssl req -new -x509 -days 365 -key ca-key.pem -sha256 -out ca.pem
match_max 100000
expect -exact "Enter pass phrase for ca-key.pem:"
send -- "${PASSPHRASE}\r"
expect -exact "\r
You are about to be asked to enter information that will be incorporated\r
into your certificate request.\r
What you are about to enter is what is called a Distinguished Name or a DN.\r
There are quite a few fields but you can leave some blank\r
For some fields there will be a default value,\r
If you enter '.', the field will be left blank.\r
-----\r
Country Name (2 letter code) \[AU\]:"
send -- "US\r"
expect -exact "US\r
State or Province Name (full name) \[Some-State\]:"
send -- "CA\r"
expect -exact "CA\r
Locality Name (eg, city) \[\]:"
send -- "SF\r"
expect -exact "SF\r
Organization Name (eg, company) \[Internet Widgits Pty Ltd\]:"
send -- "ClusterHQ\r"
expect -exact "ClusterHQ\r
Organizational Unit Name (eg, section) \[\]:"
send -- "engineering\r"
expect -exact "engineering\r
Common Name (e.g. server FQDN or YOUR name) \[\]:"
send -- "tech\r"
expect -exact "tech\r
Email Address \[\]:"
send -- "\r"
expect eof
EOF
chmod +x /tmp/docker-swarm-tls-config/createca2.exp
/tmp/docker-swarm-tls-config/createca2.exp

# Create server key and CSR.
openssl genrsa -out server-key.pem 4096
openssl req -subj "/CN=$(/usr/bin/ec2metadata --local-ipv4)" -sha256 -new -key server-key.pem -out server.csr

# Sign server public key with CA.
echo subjectAltName = IP:$(/usr/bin/ec2metadata --local-ipv4),IP:127.0.0.1 > /tmp/docker-swarm-tls-config/extfile.cnf
cat > /tmp/docker-swarm-tls-config/createserver.exp << EOF
#!/usr/bin/expect -f
set timeout -1
spawn openssl x509 -req -days 365 -sha256 -in server.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial -out server-cert.pem -extfile extfile.cnf
match_max 100000
expect -exact "Signature ok\r
subject=/CN=$(/usr/bin/ec2metadata --local-ipv4)\r
Getting CA Private Key\r
Enter pass phrase for ca-key.pem:"
send -- "${PASSPHRASE}\r"
expect eof
EOF
chmod +x /tmp/docker-swarm-tls-config/createserver.exp
/tmp/docker-swarm-tls-config/createserver.exp

# Create client key.
openssl genrsa -out key.pem 4096
openssl req -subj '/CN=client' -new -key key.pem -out client.csr
echo extendedKeyUsage = clientAuth,serverAuth > extfile.cnf
cat > /tmp/docker-swarm-tls-config/createclient.exp << EOF
#!/usr/bin/expect -f
set timeout -1
spawn openssl x509 -req -days 365 -sha256 -in client.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial -out cert.pem -extfile extfile.cnf
match_max 100000
expect -exact "Signature ok\r
subject=/CN=client\r
Getting CA Private Key\r
Enter pass phrase for ca-key.pem:"
send -- "${PASSPHRASE}\r"
expect eof
EOF
chmod +x /tmp/docker-swarm-tls-config/createclient.exp
/tmp/docker-swarm-tls-config/createclient.exp

# Set permissions.
rm -v client.csr server.csr
chmod -v 0400 ca-key.pem key.pem server-key.pem
chmod -v 0444 ca.pem server-cert.pem cert.pem

# Push certs to S3 bucket.
/usr/bin/s3cmd put --config=/root/.s3cfg --recursive /tmp/docker-swarm-tls-config/ s3://${s3_bucket}/docker-swarm-tls-config/

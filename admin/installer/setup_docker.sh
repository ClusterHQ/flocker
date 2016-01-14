#!/bin/bash
# Get CA from S3 bucket, generate certificates for local node, and restart TLS-enabled Docker daemon.
set -ex

: ${node_number:?}
: ${s3_bucket:?}

# Get expect to autofill openssl inputs.
sudo apt-get install -y expect

# Get CA from S3 bucket.
DOCKER_CERT_HOME="/root/.docker"
mkdir -p ${DOCKER_CERT_HOME}
s3cmd_wrapper get --force --config=/root/.s3cfg s3://${s3_bucket}/docker-swarm-tls-config/ca.pem "${DOCKER_CERT_HOME}"/ca.pem
s3cmd_wrapper get --force --config=/root/.s3cfg s3://${s3_bucket}/docker-swarm-tls-config/ca-key.pem "${DOCKER_CERT_HOME}"/ca-key.pem
s3cmd_wrapper get --force --config=/root/.s3cfg s3://${s3_bucket}/docker-swarm-tls-config/passphrase.txt "${DOCKER_CERT_HOME}"/passphrase.txt
PASSPHRASE=`eval cat ${DOCKER_CERT_HOME}/passphrase.txt`

# Create key and CSR.
pushd ${DOCKER_CERT_HOME}
openssl genrsa -out key.pem 4096
openssl req -subj "/CN=$(/usr/bin/ec2metadata --public-ipv4)" -sha256 -new -key ${DOCKER_CERT_HOME}/key.pem -out ${DOCKER_CERT_HOME}/node.csr

# Sign public key with CA.
echo subjectAltName = IP:$(/usr/bin/ec2metadata --public-ipv4),IP:127.0.0.1 > ${DOCKER_CERT_HOME}/extfile.cnf
echo extendedKeyUsage = clientAuth,serverAuth >> ${DOCKER_CERT_HOME}/extfile.cnf
cat > ${DOCKER_CERT_HOME}/createnode.exp << EOF
#!/usr/bin/expect -f
set timeout -1
spawn openssl x509 -req -days 365 -sha256 -in ${DOCKER_CERT_HOME}/node.csr -CA ${DOCKER_CERT_HOME}/ca.pem -CAkey ${DOCKER_CERT_HOME}/ca-key.pem -CAcreateserial -out ${DOCKER_CERT_HOME}/cert.pem -extfile ${DOCKER_CERT_HOME}/extfile.cnf
match_max 100000
expect -exact "Signature ok\r
subject=/CN=$(/usr/bin/ec2metadata --public-ipv4)\r
Getting CA Private Key\r
Enter pass phrase for ${DOCKER_CERT_HOME}/ca-key.pem:"
send -- "${PASSPHRASE}\r"
expect eof
EOF
chmod +x ${DOCKER_CERT_HOME}/createnode.exp
${DOCKER_CERT_HOME}/createnode.exp

# Set Docker defaults to enable TLS, and tag the node with ``flocker-node`` number.
cat > /etc/default/docker << EOF
DOCKER_TLS_VERIFY=1
DOCKER_CERT_PATH=/root/.docker
DOCKER_OPTS="--tlsverify --tlscacert=${DOCKER_CERT_HOME}/ca.pem --tlscert=${DOCKER_CERT_HOME}/cert.pem --tlskey=${DOCKER_CERT_HOME}/key.pem -H unix:///var/run/docker.sock -H=0.0.0.0:2375 --label flocker-node=${node_number}"
EOF

# Remove the docker machine ID (since this is a cloned AMI).
rm -f /etc/docker/key.json

# Restart Docker to enable new default settings.
service docker restart

# Wait because Docker is not ready to handle requests immediately.
sleep 10

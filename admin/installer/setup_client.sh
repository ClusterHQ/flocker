#!/bin/bash
# Setup up a client compute instance to deploy sample workloads on an install
# cluster using docker-compose.

set -ex

DOCKER_CERT_HOME="/root/.docker"
UBUNTU_HOME="/home/ubuntu"

# Get Postgres image.
apt-get update
sudo apt-get install -y postgresql-client

# Get docker-compose.
curl -L https://github.com/docker/compose/releases/download/1.5.2/docker-compose-`uname -s`-`uname -m` > /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Get uft-flocker-volumes in order to use flockerctl.
curl -sSL https://get.flocker.io/ | sh

# Get Flocker certificates.
mkdir -p /etc/flocker
s3cmd_wrapper get --recursive --config=/root/.s3cfg s3://${s3_bucket}/flocker-config/ /etc/flocker

# Get CA for Docker Swarm.
s3cmd_wrapper get --force --config=/root/.s3cfg s3://${s3_bucket}/docker-swarm-tls-config/ca.pem "${DOCKER_CERT_HOME}"/ca.pem
s3cmd_wrapper get --force --config=/root/.s3cfg s3://${s3_bucket}/docker-swarm-tls-config/ca-key.pem "${DOCKER_CERT_HOME}"/ca-key.pem
s3cmd_wrapper get --force --config=/root/.s3cfg s3://${s3_bucket}/docker-swarm-tls-config/passphrase.txt "${DOCKER_CERT_HOME}"/passphrase.txt
PASSPHRASE=`eval cat ${DOCKER_CERT_HOME}/passphrase.txt`
 
# Get expect to autofill openssl inputs.
sudo apt-get install -y expect

# Generate Docker Swarm client certificates.
pushd ${DOCKER_CERT_HOME}
openssl genrsa -out ${DOCKER_CERT_HOME}/key.pem 4096
openssl req -subj '/CN=client' -new -key ${DOCKER_CERT_HOME}/key.pem -out ${DOCKER_CERT_HOME}/client.csr
echo extendedKeyUsage = clientAuth,serverAuth > ${DOCKER_CERT_HOME}/extfile.cnf
cat > ${DOCKER_CERT_HOME}/createclient.exp << EOF
#!/usr/bin/expect -f
set timeout -1
spawn openssl x509 -req -days 365 -sha256 -in ${DOCKER_CERT_HOME}/client.csr -CA ${DOCKER_CERT_HOME}/ca.pem -CAkey ${DOCKER_CERT_HOME}/ca-key.pem -CAcreateserial -out ${DOCKER_CERT_HOME}/cert.pem -extfile ${DOCKER_CERT_HOME}/extfile.cnf
match_max 100000
expect -exact "Signature ok\r
subject=/CN=client\r
Getting CA Private Key\r
Enter pass phrase for ${DOCKER_CERT_HOME}/ca-key.pem:"
send -- "${PASSPHRASE}\r"
expect eof
EOF
chmod +x ${DOCKER_CERT_HOME}/createclient.exp
${DOCKER_CERT_HOME}/createclient.exp

# Copy Docker Certificates directory to Ubuntu's home directory.
cp -r ${DOCKER_CERT_HOME} ${UBUNTU_HOME}

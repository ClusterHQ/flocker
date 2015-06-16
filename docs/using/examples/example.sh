#!/usr/bin/env bash
set -e

# NOTE - if you are using OSX, then you need to install a version of curl that
# supports OpenSSL.  Here are the commands to install it:
#
# $ brew install curl --with-openssl
# $ brew link --force curl
# $ hash -r
# $ curl --version

# Define the control IP, port, and the certificates for authentication.

export CONTROL_SERVICE=${CONTROL_SERVICE:="54.157.8.57"}
export CONTROL_PORT=${CONTROL_PORT:="4523"}
export KEY_FILE=${KEY_FILE:="/Users/kai/projects/flocker-api-examples/flockerdemo.key"}
export CERT_FILE=${CERT_FILE:="/Users/kai/projects/flocker-api-examples/flockerdemo.crt"}
export CA_FILE=${CA_FILE:="/Users/kai/projects/flocker-api-examples/cluster.crt"}

function make-api-request() {
    local method="$1";
    local endpoint="$2";
    local data="$3";

    local url="https://${CONTROL_SERVICE}:${CONTROL_PORT}$endpoint"

    if [ "$method" == "GET" ] || [ "$method" == "DELETE" ]; then
        curl -X$method --cacert $CA_FILE --cert $CERT_FILE --key $KEY_FILE $url
        echo ""
    elif [ "$method" == "POST" ]; then
        curl -XPOST --cacert $CA_FILE --cert $CERT_FILE --key $KEY_FILE \
            --header "Content-type: application/json" -d "$data" $url
        echo ""
    else
        >&2 echo "Unknown method ${method}"
    fi
}

# Make the first request to check the service is working.
make-api-request "GET" "/v1/version"

# Create a volume.
make-api-request "POST" "/v1/configuration/datasets" \
    '{"primary": "5540d6e3-392b-4da0-828a-34b724c5bb80", "maximum_size": 107374182400, "metadata": {"name": "example_dataset"}}'
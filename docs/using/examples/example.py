import httplib
import os
import ssl
import tempfile

# NOTE - to run this example, you need at least python 2.7.9

# Define the control IP, port, and the certificates for authentication.

CONTROL_SERVICE = os.environ.get(
    "CONTROL_SERVICE", "54.157.8.57")
CONTROL_PORT = os.environ.get(
    "CONTROL_PORT", 4523)
KEY_FILE = os.environ.get(
    "KEY_FILE", "/Users/kai/projects/flocker-api-examples/flockerdemo.key")
CERT_FILE = os.environ.get(
    "CERT_FILE", "/Users/kai/projects/flocker-api-examples/flockerdemo.crt")
CA_FILE = os.environ.get(
    "CA_FILE", "/Users/kai/projects/flocker-api-examples/cluster.crt")

# Create a certificate chain and then pass that into the SSL system.

certtemp = tempfile.NamedTemporaryFile()
TEMP_CERT_CA_FILE = certtemp.name
os.chmod(TEMP_CERT_CA_FILE, 0600)
certtemp.write(open(CERT_FILE).read())
certtemp.write("\n")
certtemp.write(open(CA_FILE).read())
certtemp.seek(0)
ctx = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
ctx.load_cert_chain(TEMP_CERT_CA_FILE, KEY_FILE)

# Finally, create a HTTP connection.

c = httplib.HTTPSConnection(CONTROL_SERVICE, CONTROL_PORT, context=ctx)

def make_api_request(method, endpoint, data=None):
    if method in ("GET", "DELETE"):
        c.request(method, endpoint)
    elif method == "POST":
        c.request("POST", endpoint, data, 
            headers={"Content-type": "application/json"})
    else:
        raise Exception("Unknown method %s" % (method,))

    r = c.getresponse()
    body = r.read()
    status = r.status

    print body

# Make the first request to check the service is working.

make_api_request("GET", "/v1/version")

# Create a volume.

make_api_request("POST", "/v1/configuration/datasets",
    data= r'{"primary": "%s", "maximum_size": 107374182400, "metadata": {"name": "example_dataset"}}'
        % ("5540d6e3-392b-4da0-828a-34b724c5bb80",))
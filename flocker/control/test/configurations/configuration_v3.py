# Copyright ClusterHQ Inc.  See LICENSE file for details.

# Generate a v3 configuration.
# Hash to recreate: 26ad636ace668dbbfd224fbcd19041af31db80da

from flocker.control._model import Configuration
from flocker.control._persistence import wire_encode
from flocker.control.test.test_persistence import TEST_DEPLOYMENT

if __name__ == "__main__":
    print wire_encode(Configuration(version=3, deployment=TEST_DEPLOYMENT))

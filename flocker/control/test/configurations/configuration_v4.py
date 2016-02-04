# Copyright ClusterHQ Inc.  See LICENSE file for details.

# Generate a v4 configuration.
# Hash to recreate: 993d92c1b6a62199cf38e45afa7d2e584d48ead1

from flocker.control._model import Configuration
from flocker.control._persistence import wire_encode
from flocker.control.test.test_persistence import TEST_DEPLOYMENT

if __name__ == "__main__":
    print wire_encode(Configuration(version=4, deployment=TEST_DEPLOYMENT))

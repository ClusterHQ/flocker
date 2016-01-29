# Copyright ClusterHQ Inc.  See LICENSE file for details.

# Generate a v4 configuration.
# Hash to recreate: e99b89c0a7c036e9d50f8705871ded0c829d1a83

from flocker.control._model import Configuration
from flocker.control._persistence import wire_encode
from flocker.control.test.test_persistence import TEST_DEPLOYMENT

if __name__ == "__main__":
    print wire_encode(Configuration(version=4, deployment=TEST_DEPLOYMENT))

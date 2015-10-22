# Copyright ClusterHQ Inc.  See LICENSE file for details.

# Generate a v2 configuration.
# Commit Hash: 9db24de578a3dfa3bfbbbac8e000d30da0a2ae48

from flocker.control._model import Configuration
from flocker.control._persistence import wire_encode
from flocker.control.test.test_persistence import TEST_DEPLOYMENT

if __name__ == "__main__":
    print wire_encode(Configuration(version=2, deployment=TEST_DEPLOYMENT))

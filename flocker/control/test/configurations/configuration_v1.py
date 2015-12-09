# Copyright ClusterHQ Inc.  See LICENSE file for details.

# Generate a v1 configuration.
# Commit Hash: 7bd476e2fdc7353018ff1fc446b9b4c76e7c7c17

from flocker.control._persistence import wire_encode
from flocker.control.test.test_persistence import TEST_DEPLOYMENT

if __name__ == "__main__":
    print wire_encode(TEST_DEPLOYMENT)

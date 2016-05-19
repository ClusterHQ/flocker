# Copyright ClusterHQ Inc.  See LICENSE file for details.

# Generate a v4 configuration.
# Hash to recreate: TODO(mewert): Fill this in after you push.

from twisted.python.filepath import FilePath

from flocker.control._model import Configuration
from flocker.control._persistence import wire_encode
from flocker.control.test.test_persistence import TEST_DEPLOYMENTS

_VERSION = 4

if __name__ == "__main__":
    myfile = FilePath(__file__)
    for i, deployment in enumerate(TEST_DEPLOYMENTS, start=1):
        encoding = wire_encode(
            Configuration(version=_VERSION, deployment=deployment)
        )
        myfile.sibling(
            b"configuration_%d_v%d.json" % (i, _VERSION)
        ).setContent(encoding)

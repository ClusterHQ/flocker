# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the Flocker REST API client.
"""


def make_clientv1_tests(client_factory, synchronize_state):
    """
    Create a ``TestCase`` for testing ``IFlockerAPIV1``.

    The presumption is that the state of datasets is completely under
    control of this process. So when testing a real client it will be
    talking to a in-process server.

    :param client_factory: Callable that returns a ``IFlockerAPIV1`` provider.
    :param synchronize_state: Callable that makes state match configuration.
    """
    class InterfaceTests(TestCase):
        # The created client provides ``IFlockerAPIV1``.

        # Create returns a ``Dataset`` with matching attributes.

        # Create returns an error on conflicting dataset_id.

        # A created dataset is listed in the configuration.

        # A created dataset with custom dataset id is listed in the
        # configuration.

        # A created dataset with metadata is listed in the
        # configuration.

        # Move changes the primary of the dataset.

        # State returns information about state (uses
        # synchronize_state to populate expected information)

    return InterfaceTests


class FakeFlockerAPIV1Tests(
        InterfaceTests(FakeFlockerAPIV1,
                       lambda client: client.synchronize_state())):
    """
    Interface tests for ``FakeFlockerAPIV1``.
    """

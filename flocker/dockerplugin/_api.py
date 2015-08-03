# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
An HTTP API implementing the Docker Volumes Plugin API.

See https://github.com/docker/docker/tree/master/docs/extend for details.

We don't validate inputs with a schema since this is pre-existing code
maintained by someone else, and lacking a schema provided by Docker we
can't be sure they won't change things in minor ways. We do validate
outputs to ensure we output the documented requirements.
"""

import yaml

from twisted.python.filepath import FilePath

from klein import Klein

from ..restapi import structured

SCHEMA_BASE = FilePath(__file__).sibling(b'schema')
SCHEMAS = {
    b'/types.json': yaml.safe_load(
        SCHEMA_BASE.child(b'types.yml').getContent()),
    b'/endpoints.json': yaml.safe_load(
        SCHEMA_BASE.child(b'endpoints.yml').getContent()),
    }


class VolumePlugin(object):
    """
    An implementation of the Docker Volumes Plugin API.
    """
    app = Klein()

    def __init__(self, flocker_client, node_id):
        """
        :param IFlockerAPIV1Client flocker_client: Client that allows
            communication with Flocker.

        :param UUID node_id: The identity of the local node this plugin is
            running on.
        """
        # These parameters will get used in latter issues: FLOC-2784,
        # FLOC-2785 and FLOC-2786.
        pass

    def plugin_activate(self):
        """
        Return which Docker plugin APIs this plugin supports.
        """

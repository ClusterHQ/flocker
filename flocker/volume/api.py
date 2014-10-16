"""
A HTTP REST API for controlling the Volume Manager.
"""

from klein import Klein

from ..restapi import structured


class VolumeAPIUser(object):
    """
    A user accessing the API.
    """
    app = Klein()

    @app.route("/noop")
    @structured({}, {})
    def noop(self):
        """
        Do nothing.
        """
        return None

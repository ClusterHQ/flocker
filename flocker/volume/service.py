"""
Volume manager service, the main entry point that manages volumes.
"""

from __future__ import absolute_import

import json
from uuid import uuid4

from twisted.application.service import Service


class VolumeService(Service):
    """Main service for volume management."""

    def __init__(self, config_path):
        """
        :param config_path: :class:`FilePath`: instance pointing at the config
            file.
        """
        self._config_path = config_path

    def startService(self):
        if not self._config_path.exists():
            uuid = unicode(uuid4())
            self._config_path.setContent(json.dumps({u"uuid": uuid,
                                                     u"version": 1}))
        config = json.loads(self._config_path.getContent())
        self.uuid = config[u"uuid"]

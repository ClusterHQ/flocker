"""
Prototype interop layer between python-etcd and FilePath.
"""

# XXX Provides a synchronous API, probably not a great idea.
#
# XXX Assumes only one control service is running at a time.
# This may or may not be the case in reality.

import etcd

class EtcdFilePath(object):
    """
    An object that looks a bit like a FilePath directory but is actually
    backed onto etcd. Only supports files "one level deep" for our current
    purposes.
    """
    def __init__(self, host, port):
        self.host = host
        self.port = port

    def exists(self):
        """
        The "root directory" always exists.
        """
        return True

    def child(self, path):
        return EtcdFileNode(path, host=self.host, port=self.port)

FLOCKER_ETCD_PATH = "/flocker/"

class EtcdFileNode(object):
    """
    An object that looks a bit like a FilePath file but is actually backed
    onto etcd.
    """
    def __init__(self, path, host, port):
        self.path = path
        self.client = etcd.Client(host=host, port=port)

    def exists(self):
        try:
            self.client.get(self.path)
            return True
        except KeyError:
            return False

    def setContent(self, content):
        self.client.write(FLOCKER_ETCD_PATH + self.path, content)

    def getContent(self):
        return self.client.read(FLOCKER_ETCD_PATH + self.path).value

    def moveTo(self):
        raise Exception("etcd persistence cannot be used in "
                        "conjunction with v1 configs")

"""
Limits for CloudFormation Installer.
"""

MIN_CLUSTER_SIZE = 3
MAX_CLUSTER_SIZE = 10
CLUSTER_SIZE_TEMPLATE = u"Supported cluster sizes: min={0} max={1}".format(
    MIN_CLUSTER_SIZE, MAX_CLUSTER_SIZE)


class InvalidClusterSizeException(Exception):
    """
    """
    def __init__(self, size):
        message = ". ".join([
            u"The requested cluster size of {0} is not supported".format(size),
            CLUSTER_SIZE_TEMPLATE])
        Exception.__init__(self, message, size)
        self.size = size

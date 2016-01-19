import random


class EmptyClusterError(Exception):
    """
    Exception indicating that the cluster contains no nodes.
    """


def select_node(nodes):
    """
    Select a node from a list of nodes.

    :param Sequence[Node] nodes: Sequence of nodes.
    :return Node: Selected node.
    """
    if nodes:
        return random.choice(nodes)
    else:
        raise EmptyClusterError("Cluster contains no nodes.")

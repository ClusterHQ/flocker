# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Helper utilities for CloudFormation Installer's Packer images.
"""
from pyrsistent import freeze


class _PackerOutputParser(object):
    """
    Parse the output of ``packer -machine-readable``.
    """
    def __init__(self):
        self.artifacts = []
        self._current_artifact = {}

    def _parse_line_ARTIFACT(self, parts):
        """
        Parse line parts containing information about an artifact.

        :param list parts: The parts of resulting from splitting a comma
            separated packer output line.
        """
        artifact_type = parts[1]
        if parts[4] == 'end':
            self._current_artifact['type'] = artifact_type
            self.artifacts.append(freeze(self._current_artifact))
            self._current_artifact = {}
            return
        key = parts[4]
        value = parts[5:]
        if len(value) == 1:
            value = value[0]
        self._current_artifact[key] = value

    def parse_line(self, line):
        """
        Parse a line of ``packer`` machine readable output.

        :param unicode line: A line to be parsed.
        """
        parts = line.rstrip().split(",")
        if len(parts) >= 3:
            if parts[2] == 'artifact':
                self._parse_line_ARTIFACT(parts)

    def packer_amis(self):
        """
        :return: A ``dict`` of ``{aws_region: ami_id}`` found in the
            ``artifacts``.
        """
        for artifact in self.artifacts:
            if artifact['type'] == 'amazon-ebs':
                return _unserialize_packer_dict(artifact["id"])
        return freeze({})


def _unserialize_packer_dict(serialized_packer_dict):
    """
    Parse a packer serialized dictionary.

    :param unicode serialized_packer_dict: The serialized form.
    :return: A ``dict`` of the keys and values found.
    """
    packer_dict = {}
    for item in serialized_packer_dict.split("%!(PACKER_COMMA)"):
        key, value = item.split(":")
        packer_dict[key] = value
    return freeze(packer_dict)

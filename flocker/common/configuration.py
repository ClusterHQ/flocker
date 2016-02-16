# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Helpers for loading and parsing YAML configuration.
"""


class MissingConfigError(Exception):
    """
    Error that is raised to indicate that some required configuration key was
    not specified.
    """
    pass


class Optional(object):
    """
    Object for configuring optional configuration values.
    """

    def __init__(self, default, description):
        self.default = default
        self.description = description

    def __repr__(self):
        return "{} (optional default={})".format(self.description,
                                                 repr(self.default))


def _is_optional(substructure):
    """
    Determines if a substructure is an optional part of the configuration.
    """
    if type(substructure) == Optional:
        return True
    if type(substructure) is dict:
        for value in substructure.values():
            if not _is_optional(value):
                return False
        return True
    return False


def extract_substructure(base, substructure):
    """
    Assuming that substructure is a possibly nested dictionary, return a new
    dictionary with the same keys (and subkeys) as substructure, but extract
    the leaf values from base.

    This is used to extract and verify a configuration from a yaml blob.
    """
    if (type(substructure) is not dict and
            type(base) is not dict):
        return base
    if type(base) is not dict:
        raise MissingConfigError(
            "Found non-dict value {} when expecting a sub-configuration "
            "{}.".format(repr(base), repr(substructure)))
    if type(substructure) is not dict:
        raise MissingConfigError(
            "Found dict value {} when expecting a simple configuration value "
            "{}.".format(repr(base), repr(substructure)))
    try:
        subdict = []
        for key, value in substructure.iteritems():
            if type(value) is Optional:
                base_val = base.get(key, value.default)
            elif _is_optional(value):
                base_val = base.get(key, {})
            else:
                base_val = base[key]
            subdict.append((key, extract_substructure(base_val, value)))
        return dict(subdict)
    except KeyError as e:
        raise MissingConfigError(
            "Missing key {} in configuration".format(e.args[0]))

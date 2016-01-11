# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Functions for checking a method name provided by the user.
"""


class InvalidMethod(Exception):
    """
    Method not meeting requested criteria.
    """


def validate_no_arg_method(interface, method_name):
    """
    Check that method name exists in interface and requires no parameters.

    :param zope.interface.Interface interface: Interface to validate against.
    :param str method_name: Method name to validate.
    :raise InvalidMethod: if name is not valid or requires parameters.
    """
    for name, method in interface.namesAndDescriptions():
        if name == method_name:
            if len(method.getSignatureInfo()['required']) > 0:
                raise InvalidMethod(
                    'Method {!r} requires parameters'.format(method_name)
                )
            return
    raise InvalidMethod(
        'Method {!r} not found in interface {}'.format(
            method_name, interface.__name__)
    )

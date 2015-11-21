# Copyright ClusterHQ Ltd.  See LICENSE file for details.

"""
Testing utilities for ``flocker.dockerplugin`.
"""

from bitmath import TiB, GiB, MiB, KiB


def parse_num(expression):
    """
      Parse a string of a dataset size 10g, 100kib etc into
      a usable integer

      :param expression: the dataset expression to parse.
    """
    if not expression:
        return None
    expression = expression.encode("ascii")
    unit = expression.translate(None, "1234567890.")
    num = int(expression.replace(unit, ""))
    unit = unit.lower()
    if unit == 'tb' or unit == 't' or unit == 'tib':
        return int(TiB(num).to_Byte().value)
    elif unit == 'gb' or unit == 'g' or unit == 'gib':
        return int(GiB(num).to_Byte().value)
    elif unit == 'mb' or unit == 'm' or unit == 'mib':
        return int(MiB(num).to_Byte().value)
    elif unit == 'kb' or unit == 'k' or unit == 'kib':
        return int(KiB(num).to_Byte().value)
    # this may parse a number 15giib to 15bytes becase
    # of user error, should we handle this better?
    else:
        return int(num)

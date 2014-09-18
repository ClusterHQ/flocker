# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from enchant.tokenize import Filter

class IgnoreVersionFilter(Filter):
    """
    If a word is part of Flocker's version, ignore it.
    """

    def _skip(self, word):
        return word in version

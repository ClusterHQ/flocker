# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Filters for Sphinx.

A separate module than conf.py so that Sphinx can pickle instances of classes
defined here.
"""

from characteristic import attributes
from enchant.tokenize import Filter


# See http://doughellmann.com/2011/05/26/creating-a-spelling-checker-for-restructuredtext-documents.html
@attributes(['words'])
class IgnoreWordsFilter(Filter):
    """
    Given a set of words ignore them all.
    """
    def __init__(self, tokenizer):
        Filter.__init__(self, tokenizer)

    def _skip(self, word):
        return word in self.words


@attributes(['words'])
class IgnoreWordsFilterFactory(object):
    """
    Factory for ``IgnoreWordsFilter``.
    """

    def __call__(self, tokenizer):
        return IgnoreWordsFilter(tokenizer, words=self.words)

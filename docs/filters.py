# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Filters for Sphinx.

A separate module than conf.py so that Sphinx can pickle instances of classes
defined here.
"""

from enchant.tokenize import Filter

# See http://doughellmann.com/2011/05/26/creating-a-spelling-checker-for-restructuredtext-documents.html
class IgnoreWordsFilter(Filter):
    """
    Given a set of words ignore them all.
    """
    def __init__(self, tokenizer, word_set):
        self.word_set = word_set
        Filter.__init__(self, tokenizer)

    def _skip(self, word):
        return word in self.word_set


class IgnoreWordsFilterFactory(object):
    """
    Factory for ``IgnoreWordsFilter``.
    """

    def __init__(self, words):
        self.words = words

    def __call__(self, tokenizer):
        return IgnoreWordsFilter(tokenizer, self.words)

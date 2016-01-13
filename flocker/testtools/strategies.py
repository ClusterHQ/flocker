# Copyright ClusterHQ Inc.  See LICENSE file for details.

from hypothesis.strategies import lists, text
from twisted.python.filepath import FilePath


path_segments = (
    text().
    filter(lambda x: '/' not in x).
    map(lambda x: x.encode('utf8')).
    filter(lambda x: '\0' not in x))
"""
Individual path segments.

These are UTF-8 encoded segments that contain neither '/' nor NULL.

e.g. 'foo', 'rc.local'.
"""


paths = lists(path_segments).map(lambda ps: FilePath('/'.join(ps)))
"""
Paths

e.g. '/usr/local', 'foo/bar/bar'.
"""

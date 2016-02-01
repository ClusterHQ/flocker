# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Filter Eliot logs out of Twisted test.log.
"""

import sys

from flocker.testtools import extract_eliot_from_twisted_log


def chain_files(paths):
    """
    Iterate through many files, line by line.
    """
    for path in paths:
        with open(path, 'r') as f:
            for line in f:
                yield line


def process_line(line):
    eliot_line = extract_eliot_from_twisted_log(line)
    if eliot_line:
        yield eliot_line
        yield '\n'


def filter_eliot_main(args, base_path, top_level, stdin=None, stdout=None):
    """
    Filter logs.

    :param args: Iterable of file names to read logs from. If empty, reads
        from stdin.
    :param FilePath base_path: The path to the executable.
    :param FilePath top_level: The path to the directory where the flocker
        package is.
    :param file stdin: File-like object to read from if ``args`` is empty.
        If ``None``, defaults to STDIN.
    :param file stdout: File-like object to write filtered logs to. If
        ``None``, defaults to STDOUT.
    """
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    if args:
        lines = chain_files(args)
    else:
        lines = stdin
    for line in lines:
        for output in process_line(line):
            stdout.write(output)

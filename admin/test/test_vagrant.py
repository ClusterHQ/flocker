# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Tests for :module:`admin.vagrant`.
"""

from twisted.python.filepath import FilePath
from twisted.python.usage import UsageError

from admin.vagrant import (
    box_metadata, BuildOptions)

from flocker import __version__ as flocker_version
from flocker.testtools import TestCase


class BuildOptionsTest(TestCase):
    """
    Tests for :class:`admin.vagrant.BuildOptions`.
    """

    def test_relative_args(self):
        """
        When invoked as `build`, no box can be specified. BuildOption takes the
        path from the parent of :file:`build`, and the box name from the name
        of
        that directory.
        """
        path = FilePath(self.mktemp())
        path.createDirectory()
        base_path = path.descendant(['somewhere', 'box-name', 'build'])

        options = BuildOptions(base_path=base_path, top_level=path)

        options.parseOptions([])

        self.assertEqual(options, {
            'box': 'box-name',
            'path': path.descendant(['somewhere', 'box-name']),
            'build-server': 'http://build.clusterhq.com/',
            'branch': None,
            'flocker-version': flocker_version,
        })

    def test_relative_args_with_box(self):
        """
        When invoked as `build`, no box can be specified.
        """
        path = FilePath(self.mktemp())
        path.createDirectory()
        base_path = path.descendant(['somewhere', 'box-name', 'build'])

        options = BuildOptions(base_path=base_path, top_level=path)

        self.assertRaises(UsageError, options.parseOptions, ['--box', 'box'])

    def test_absolute_args(self):
        """
        When invoked as `build-vagrant-box`, :class:`BuildOption` takes the
        path relative to the top-level, and the box name from the passed
        argument.
        """
        path = FilePath(self.mktemp())
        path.createDirectory()
        base_path = path.descendant(['bin', 'build-vagrant-box'])

        options = BuildOptions(base_path=base_path, top_level=path)

        options.parseOptions(['--box', 'box-name'])

        self.assertEqual(options, {
            'box': 'box-name',
            'path': path.descendant(['vagrant', 'box-name']),
            'build-server': 'http://build.clusterhq.com/',
            'branch': None,
            'flocker-version': flocker_version,
        })

    def test_absolute_args_no_box(self):
        """
        When invoked as `build-vagrant-box`, specifying a box is required.
        """
        path = FilePath(self.mktemp())
        path.createDirectory()
        base_path = path.descendant(['bin', 'build-vagrant-box'])

        options = BuildOptions(base_path=base_path, top_level=path)

        self.assertRaises(UsageError, options.parseOptions, [])


class MetadataTests(TestCase):
    """
    Tests for :func:`box_metadata`.
    """

    def test_with_version(self):
        """
        `box_metadata` returns the metadata required to add a box locally.
        """
        metadata = box_metadata("box-name", "0.1.2.3-gxx-dirty",
                                FilePath('/some/path'))
        self.assertEqual(metadata, {
            "name": "clusterhq/box-name",
            "description": "Test clusterhq/box-name box.",
            "versions": [{
                "version": "0.1.2.3.gxx.dirty",
                "providers": [{
                    "name": "virtualbox",
                    "url": "/some/path",
                }]
            }]})

    def test_without_version(self):
        """
        When a version is not provided, the verson defaults to 0.
        """
        metadata = box_metadata("box-name", '', FilePath('/some/path'))
        self.assertEqual(metadata, {
            "name": "clusterhq/box-name",
            "description": "Test clusterhq/box-name box.",
            "versions": [{
                "version": "0",
                "providers": [{
                    "name": "virtualbox",
                    "url": "/some/path",
                }]
            }]})

    def test_url_escaped(self):
        """
        When a URL includes special characters, they are escaped so that
        Vagrant can download the box from Amazon S3 without getting 403 errors.

        "/" and ":" are not escaped (these only appear in the protocol).
        """
        metadata = box_metadata("box-name", "0.1.2.3-gxx-dirty",
                                FilePath('/some/path/with/+/and/:'))
        self.assertEqual(metadata, {
            "name": "clusterhq/box-name",
            "description": "Test clusterhq/box-name box.",
            "versions": [{
                "version": "0.1.2.3.gxx.dirty",
                "providers": [{
                    "name": "virtualbox",
                    "url": "/some/path/with/%2B/and/:",
                }]
            }]})

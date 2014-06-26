# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Tests for :module:`flocker.common.docker`."""

from twisted.trial.unittest import TestCase

from ...testtools import WithInitTestsMixin
from ..docker import UnknownContainer

class UnknownContainerTests(WithInitTestsMixin, TestCase):
    record_type = UnknownContainer
    values = dict(container_name=b'busybox-app')

# -*- coding: utf-8 -*-
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from twisted.trial.unittest import TestCase
from ..testtools import FlockerScriptTestsMixin
from ..script import CLIScript, CLIOptions


class FlockerDeployTests(FlockerScriptTestsMixin, TestCase):
    """Tests for ``flocker-deploy``."""
    script = CLIScript
    options = CLIOptions
    command_name = u'flocker'
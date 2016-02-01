# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Tests for ``admin.installer``.
"""
from textwrap import dedent

from pyrsistent import PClass, field, pmap_field

from flocker.testtools import (
    TestCase
)

from ..installer._images import (
    _packer_amis, _PackerOutputParser,
)


class ParserData(PClass):
    input = field(type=unicode, mandatory=True)
    output = pmap_field(key_type=unicode, value_type=unicode, optional=False)


PACKER_OUTPUT_US_WEST_1 = ParserData(
    input=u"""\
1450420216,,ui,say,Build 'amazon-ebs' finished.
1450420216,,ui,say,\n==> Builds finished. \
The artifacts of successful builds are:
1450420216,amazon-ebs,artifact-count,1
1450420216,amazon-ebs,artifact,0,builder-id,mitchellh.amazonebs
1450420216,amazon-ebs,artifact,0,id,us-west-1:ami-e098f380
1450420216,amazon-ebs,artifact,0,string,AMIs were created:\n\n\
us-west-1: ami-e098f380
1450420216,amazon-ebs,artifact,0,files-count,0
1450420216,amazon-ebs,artifact,0,end
1450420216,,ui,say,--> amazon-ebs: AMIs were created:\n\n\
us-west-1: ami-e098f380
""",
    output={u"us-west-1": u"ami-e098f380"}
)

PACKER_OUTPUT_US_ALL = ParserData(
    input=u"""\
1450420216,,ui,say,Build 'amazon-ebs' finished.
1450420216,,ui,say,\n==> Builds finished. \
The artifacts of successful builds are:
1450420216,amazon-ebs,artifact-count,1
1450420216,amazon-ebs,artifact,0,builder-id,mitchellh.amazonebs
1450420216,amazon-ebs,artifact,0,id,\
us-east-1:ami-dc4410b6%!(PACKER_COMMA)\
us-west-1:ami-e098f380%!(PACKER_COMMA)\
us-west-2:ami-8c8f90ed
1450420216,amazon-ebs,artifact,0,string,AMIs were created:\n\n\
us-east-1: ami-dc4410b6\n\
us-west-1: ami-e098f380\n\
us-west-2: ami-8c8f90ed
1450420216,amazon-ebs,artifact,0,files-count,0
1450420216,amazon-ebs,artifact,0,end
1450420216,,ui,say,--> amazon-ebs: AMIs were created:\n\n\
us-east-1: ami-dc4410b6\n\
us-west-1: ami-e098f380\n\
us-west-2: ami-8c8f90ed
""",
    output={
        u"us-east-1": u"ami-dc4410b6",
        u"us-west-1": u"ami-e098f380",
        u"us-west-2": u"ami-8c8f90ed",
    }
)


PACKER_OUTPUT_NONE = ParserData(
    input=u"""\
1450420216,,ui,say,Build 'amazon-ebs' finished.
""",
    output={},
)


class PackerAmisTests(TestCase):
    """
    Tests for ``_packer_amis``.
    """
    def assert_packer_amis(self, parser_data):
        parser = _PackerOutputParser.parse_string(parser_data.input)
        self.assertEqual(parser_data.output, _packer_amis(parser))

    def test_no_ami(self):
        """
        If there are no AMI artifacts, the return value is ``None``.
        """
        self.assert_packer_amis(PACKER_OUTPUT_NONE)

    def test_one_ami(self):
        """
        If there is a single AMI artifact, the return value is a single item
        dictionary.
        """
        self.assert_packer_amis(PACKER_OUTPUT_US_WEST_1)

    def test_multiple_ami(self):
        """
        """
        self.assert_packer_amis(PACKER_OUTPUT_US_ALL)

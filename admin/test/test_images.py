# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Tests for ``admin.installer``.
"""
import json
from unittest import skipIf

import boto3
from botocore.exceptions import (
    ClientError, NoCredentialsError, EndpointConnectionError
)

from effect import Effect, sync_perform
from effect.testing import perform_sequence

from txeffect import perform as async_perform

from pyrsistent import PClass, field, pmap_field, thaw

from testtools.content import text_content

from twisted.internet.error import ProcessTerminated
from twisted.python.filepath import FilePath

from flocker.testtools import (
    AsyncTestCase, TestCase, random_name, FakeSysModule
)

from ..installer._images import (
    _PublishInstallerImagesMain, WriteToS3, PackerBuild,
    _PackerOutputParser, DISPATCHER, PackerConfigure,
)

try:
    boto3.session.Session().client('s3').list_buckets()
except (ClientError, NoCredentialsError, EndpointConnectionError) as e:
    S3_INACCESSIBLE = True
    S3_INACCESSIBLE_REASON = (
        "S3 is not accessible. "
        "Check AWS credentials in ~/.aws/credentials. "
        "Error was: {!r}"
    ).format(e)
    del e
else:
    S3_INACCESSIBLE = False
    S3_INACCESSIBLE_REASON = ""

PACKER_OUTPUTS = FilePath(__file__).sibling('packer_outputs')


class ParserData(PClass):
    """
    A record to store sample input and output which can be used to test the
    PackerOutputParser.

    ;ivar FilePath input: A file containing sample ``packer build
         -machine-readable`` output which will be fed into the parser.
    :ivar pmap output: The expected dictionary of the regional AMI values after
        parsing ``input``.
    """
    input = field(type=FilePath, mandatory=True)
    output = pmap_field(key_type=unicode, value_type=unicode, optional=False)


# These are sample outputs of running ``packer build -machine-readable`` with
# configuration files which result in Packer publishing AMI images to multiple
# or one Amazon region.
PACKER_OUTPUT_US_ALL = ParserData(
    input=PACKER_OUTPUTS.child('PACKER_OUTPUT_US_ALL'),
    output={
        u"us-east-1": u"ami-dc4410b6",
        u"us-west-1": u"ami-e098f380",
        u"us-west-2": u"ami-8c8f90ed",
    }
)

PACKER_OUTPUT_US_WEST_1 = ParserData(
    input=PACKER_OUTPUTS.child('PACKER_OUTPUT_US_WEST_1'),
    output={u"us-west-1": u"ami-e098f380"}
)

# This is an example of running ``packer build -machine-readble`` with a
# configuration file that has no builders.
PACKER_OUTPUT_NONE = ParserData(
    input=PACKER_OUTPUTS.child('PACKER_OUTPUT_NONE'),
    output={},
)


class PackerOutputParserTests(TestCase):
    def test_artifact(self):
        """
        An artifact is recorded when the first ``end`` parameter is
        encountered.
        """
        parser = _PackerOutputParser()
        parser.parse_line(
            '1450420216,amazon-ebs,artifact,0,builder-id,mitchellh.amazonebs\n'
        )
        parser.parse_line('1450420216,amazon-ebs,artifact,0,end\n')
        self.assertEqual(
            [{u'type': u'amazon-ebs',
              u'builder-id': u'mitchellh.amazonebs'}],
            parser.artifacts
        )

    def test_artifact_multiple(self):
        """
        An artifact is appended when another ``end`` parameter is encountered.
        """
        parser = _PackerOutputParser()
        parser.parse_line('1450420216,amazon-ebs,artifact,0,end\n')
        parser.parse_line('1450420216,foobar,artifact,0,end\n')
        self.assertEqual(
            [{'type': 'amazon-ebs'},
             {'type': 'foobar'}],
            parser.artifacts
        )


class PackerAmisTests(TestCase):
    """
    Tests for ``PackerOutputParser.packer_amis``.
    """
    def assert_packer_amis(self, parser_data):
        parser = _PackerOutputParser()
        with parser_data.input.open('r') as f:
            for line in f:
                parser.parse_line(line)
        self.assertEqual(parser_data.output, parser.packer_amis())

    def test_no_ami(self):
        """
        If there are no AMI artifacts, the return value is an empty dictionary.
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


class PackerConfigureTests(TestCase):
    """
    Tests for ``PackerConfigure``.
    """
    def setUp(self):
        super(PackerConfigureTests, self).setUp()
        self.working_directory = FilePath(self.mktemp())
        self.working_directory.makedirs()

    def test_configuration(self):
        expected_build_region = random_name(self)
        expected_publish_regions = [random_name(self)]
        expected_source_ami = random_name(self)
        intent = PackerConfigure(
            build_region=expected_build_region,
            publish_regions=expected_publish_regions,
            source_ami=expected_source_ami,
            template=u"docker",
            distribution=u"ubuntu-14.04",
            working_directory=self.working_directory,
        )
        packer_configuration_path = sync_perform(
            dispatcher=DISPATCHER,
            effect=Effect(intent=intent)
        )
        with packer_configuration_path.open('r') as f:
            packer_configuration = json.load(f)

        [builder] = packer_configuration["builders"]
        build_region = builder['region']
        build_source_ami = builder['source_ami']
        publish_regions = builder['ami_regions']
        [provisioner] = packer_configuration["provisioners"]
        self.assertEqual(
            (expected_build_region, set(expected_publish_regions),
             expected_source_ami),
            (build_region, set(publish_regions),
             build_source_ami)
        )


class PackerBuildIntegrationTests(AsyncTestCase):
    """
    Integration tests for ``PackerBuild``.
    """
    def setUp(self):
        super(PackerBuildIntegrationTests, self).setUp()
        self.sys_module = FakeSysModule()
        self.addCleanup(
            lambda: self.addDetail(
                name="stderr",
                content_object=text_content(
                    self.sys_module.stderr.getvalue()
                )
            )
        )

    def perform_packer_build(self, template):
        from twisted.internet import reactor
        d = async_perform(
            dispatcher=DISPATCHER,
            effect=Effect(
                intent=PackerBuild(
                    reactor=reactor,
                    template=template,
                    sys_module=self.sys_module,
                )
            )
        )
        return d

    def test_template_error(self):
        """
        Template errors result in the process exiting and an error message
        printed to stderr.
        """
        template = FilePath(self.mktemp())
        template.setContent("")

        d = self.perform_packer_build(template)

        d = self.assertFailure(d, ProcessTerminated)

        def check_error(exception):
            self.assertEqual(1, exception.exitCode)
            self.assertIn(
                "Failed to parse template", self.sys_module.stderr.getvalue()
            )
        return d.addCallback(check_error)


class WriteToS3Tests(TestCase):
    """
    Tests for ``WriteToS3``.
    """
    @skipIf(S3_INACCESSIBLE, S3_INACCESSIBLE_REASON)
    def setUp(self):
        super(WriteToS3Tests, self).setUp()
        self.s3client = boto3.client("s3")
        self.bucket_name = random_name(self).lower().replace("_", "")
        self.key_name = random_name(self)
        self.s3client.create_bucket(Bucket=self.bucket_name)

        def cleanup():
            self.s3client.delete_object(
                Bucket=self.bucket_name,
                Key=self.key_name,
            )
            self.s3client.delete_bucket(Bucket=self.bucket_name)
        self.addCleanup(cleanup)

    def assert_object_content(self, key, expected_content):
        self.assertEqual(
            expected_content,
            self.s3client.get_object(
                Bucket=self.bucket_name,
                Key=key
            )["Body"].read()
        )

    def test_perform(self):
        """
        """
        intent = WriteToS3(
            content=random_name(self).encode('ascii'),
            target_key=self.key_name,
            target_bucket=self.bucket_name,
        )
        result = sync_perform(
            dispatcher=DISPATCHER,
            effect=Effect(intent=intent)
        )
        self.assertIs(None, result)
        self.assert_object_content(
            key=intent.target_key,
            expected_content=intent.content
        )


def packer_publish_sequence(reactor, working_directory, template,
                            source_ami, ami_map, options):
    template_path = working_directory.child('packer_configuration')
    return [
        (PackerConfigure(
            build_region=options["build_region"],
            publish_regions=options["regions"],
            source_ami=source_ami,
            working_directory=working_directory,
            template=template,
            distribution=options["distribution"],
        ), lambda intent: template_path),
        (PackerBuild(
            reactor=reactor,
            template=template_path,
        ), lambda intent: ami_map),
        (WriteToS3(
            content=json.dumps(
                thaw(ami_map),
                encoding='utf-8',
            ),
            target_bucket=options["target_bucket"],
            target_key=template,
        ), lambda intent: None),
    ]


class PackerInstallerImagesMainTests(TestCase):
    """
    Tests for ``_PublishInstallerImagesMain``
    """
    def test_sequence(self):
        """
        The main function performs a sequence of effects.
        """
        script = _PublishInstallerImagesMain(
            working_directory=FilePath(self.mktemp())
        )
        reactor = object()
        options = script._parse_options([])
        result = perform_sequence(
            seq=packer_publish_sequence(
                reactor=reactor,
                template=u"docker",
                options=options,
                working_directory=script.working_directory,
                source_ami=options["source_ami"],
                ami_map=PACKER_OUTPUT_US_ALL.output,
            ),
            eff=script.main_effect(
                reactor=reactor, options=options
            )
        )
        self.assertEqual(
            PACKER_OUTPUT_US_ALL.output,
            result
        )

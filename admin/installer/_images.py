# -*- test-case-name: admin.test.test_images -*-
# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Helper utilities for CloudFormation Installer's Packer images.
"""
import json
import sys
from tempfile import mkdtemp

import boto3

from effect import (
    Effect, ComposedDispatcher, TypeDispatcher,
    sync_performer, base_dispatcher,
)
from effect.do import do, do_return

from txeffect import deferred_performer, perform as async_perform

from pyrsistent import PClass, field, freeze, thaw, pvector_field, CheckedPVector

from twisted.python.constants import ValueConstant, Values
from twisted.python.filepath import FilePath
from twisted.python.usage import Options, UsageError

from flocker.common.runner import run


PACKER_TEMPLATE_DIR = FilePath(__file__).sibling('packer')


class RegionConstant(ValueConstant):
    """
    The name of a cloud region.
    """


class Regions(CheckedPVector):
    __type__ = RegionConstant


# The AWS regions supported by Packer.
# XXX ap-northeast-2 is not supported by the current packer release:
# https://github.com/mitchellh/packer/issues/3058
class AWS_REGIONS(Values):
    """
    Constants representing supported target packaging formats.
    """
    AP_NORTHEAST_1 = RegionConstant(u"ap-northeast-1")
    AP_SOUTHEAST_1 = RegionConstant(u"ap-southeast-1")
    AP_SOUTHEAST_2 = RegionConstant(u"ap-southeast-2")
    EU_CENTRAL_1 = RegionConstant(u"eu-central-1")
    EU_WEST_1 = RegionConstant(u"eu-west-1")
    SA_EAST_1 = RegionConstant(u"sa-east-1")
    US_EAST_1 = RegionConstant(u"us-east-1")
    US_WEST_1 = RegionConstant(u"us-west-1")
    US_WEST_2 = RegionConstant(u"us-west-2")

# Hard coded Ubuntu 14.04 base AMI.
# XXX These AMIs are constantly being updated.
# This should be looked up dynamically using Canonical's AWS owner ID
# 099720109477. See:
# https://askubuntu.com/a/53586
SOURCE_AMIS = {
    u"ubuntu-14.04": {
        AWS_REGIONS.US_WEST_2: u"ami-56f59e36",
    }
}

DEFAULT_IMAGE_BUCKET = u'clusterhq-installer-images'
DEFAULT_BUILD_REGION = AWS_REGIONS.US_WEST_2
DEFAULT_DISTRIBUTION = u"ubuntu-14.04"
DEFAULT_AMI = SOURCE_AMIS[DEFAULT_DISTRIBUTION][DEFAULT_BUILD_REGION]
DEFAULT_TEMPLATE = u"docker"


class _PackerOutputParser(object):
    """
    Parse the output of ``packer -machine-readable``.
    """
    def __init__(self):
        self.artifacts = []
        self._current_artifact = {}

    def _parse_line_ARTIFACT(self, parts):
        """
        Parse line parts containing information about an artifact.

        :param list parts: The parts of resulting from splitting a comma
            separated packer output line.
        """
        artifact_type = parts[1]
        if parts[4] == 'end':
            self._current_artifact['type'] = artifact_type
            self.artifacts.append(freeze(self._current_artifact))
            self._current_artifact = {}
            return
        key = parts[4]
        value = parts[5:]
        if len(value) == 1:
            value = value[0]
        self._current_artifact[key] = value

    def parse_line(self, line):
        """
        Parse a line of ``packer`` machine readable output.

        :param unicode line: A line to be parsed.
        """
        parts = line.rstrip().split(",")
        if len(parts) >= 3:
            if parts[2] == 'artifact':
                self._parse_line_ARTIFACT(parts)

    def packer_amis(self):
        """
        :return: A ``dict`` of ``{aws_region: ami_id}`` found in the
            ``artifacts``.
        """
        for artifact in self.artifacts:
            if artifact['type'] == 'amazon-ebs':
                return _unserialize_packer_dict(artifact["id"])
        return freeze({})


def _unserialize_packer_dict(serialized_packer_dict):
    """
    Parse a packer serialized dictionary.

    :param unicode serialized_packer_dict: The serialized form.
    :return: A ``dict`` of the keys and values found.
    """
    packer_dict = {}
    for item in serialized_packer_dict.split("%!(PACKER_COMMA)"):
        key, value = item.split(":")
        packer_dict[key] = value
    return freeze(packer_dict)


class _ConfigurationEncoder(json.JSONEncoder):
    """
    JSON encoder that can encode ValueConstant etc.
    """
    def default(self, obj):
        if isinstance(obj, ValueConstant):
            return obj.value
        return JSONEncoder.default(self, obj)


def _json_dump(obj, fp):
    return json.dump(obj, fp, cls=_ConfigurationEncoder)


class PackerConfigure(PClass):
    """
    The attributes necessary to create a custom packer configuration file from
    the prototype files in ``admin/installer/packer``.

    :ivar build_region: The AWS region to build images in.
    :ivar publish_regions: The AWS regions to publish the build images to.
    :ivar template: The prototype configuration to use as a base. One of
        `docker` or `flocker`.
    :ivar distribution: The operating system distribution to install.
        ubuntu-14.04 is the only one implemented so far.
    :ivar configuration_directory: The directory containing prototype
        configuration templates.
    :ivar source_ami: The AMI ID to use as the base image.
    :ivar working_directory: The directory in which templates will be copied
        and modified.
    """
    build_region = field(type=RegionConstant, mandatory=True)
    publish_regions = pvector_field(item_type=RegionConstant)
    template = field(type=unicode, mandatory=True)
    distribution = field(type=unicode, mandatory=True)
    configuration_directory = field(type=FilePath, initial=PACKER_TEMPLATE_DIR)
    source_ami = field(type=unicode, mandatory=True)
    working_directory = field(type=FilePath, mandatory=True)


@sync_performer
def perform_packer_configure(dispatcher, intent):
    """
    Copy the prototype configuration files and provisioning scripts to a
    temporary location and modify one of the configurations witht the values
    found in ``intent``.
    """
    temporary_configuration_directory = intent.working_directory.child(
        'packer_configuration'
    )
    temporary_configuration_directory.makedirs()
    intent.configuration_directory.copyTo(temporary_configuration_directory)

    template_name = (
        u"template_{distribution}_{template}.json".format(
            distribution=intent.distribution,
            template=intent.template,
        )
    )
    template_path = temporary_configuration_directory.child(
        template_name
    )

    with template_path.open('r') as infile:
        configuration = json.load(infile)

    # If a region was specified, just build the image there and don't do
    # any copying.
    configuration['builders'][0]['region'] = intent.build_region
    configuration['builders'][0]['source_ami'] = intent.source_ami
    configuration['builders'][0]['ami_regions'] = thaw(intent.publish_regions)
    output_template_path = template_path.temporarySibling()
    with output_template_path.open('w') as outfile:
        _json_dump(configuration, outfile)
    # XXX temporarySibling sets alwaysCreate = True for some reason.
    output_template_path.alwaysCreate = False
    return output_template_path


class PackerBuild(PClass):
    """
    The attributes necessary to run ``packer build``.

    # XXX This attribute should be called configuration_path
    :ivar template: The path to a packer build configuration file.
    :ivar reactor: The Twisted reactor object used to run the ``packer build``
        subprocess.
    :ivar sys_module: A ``sys`` like object with ``stdout`` and ``stderr``
        attributes. The ``stderr`` of ``packer build`` will be written to
        ``sys_module.stderr``.
    """
    template = field(type=FilePath)
    reactor = field(mandatory=True)
    sys_module = field(initial=sys)


@deferred_performer
def perform_packer_build(dispatcher, intent):
    """
    Run ``packer build`` using the configuration in the supplied ``intent`` and
    parse its output.

    :returns: A ``Deferred`` which fires with a dict mapping the ID of the AMI
        published to each AWS region.
    """
    command = ['/opt/packer/packer', 'build',
               '-machine-readable', intent.template.path]
    parser = _PackerOutputParser()

    def handle_stdout(line):
        parser.parse_line(line)
        intent.sys_module.stderr.write(line + "\n")
    d = run(intent.reactor, command, handle_stdout=handle_stdout)
    d.addCallback(lambda ignored: parser.packer_amis())
    return d


class WriteToS3(PClass):
    """
    The attributes necessary to write bytes to an S3 bucket.

    :ivar content: The bytes to write.
    :ivar target_bucket: The name of the S3 bucket.
    :ivar target_key: The name of the object which will be created in the S3
        bucket.
    """
    content = field(type=bytes, mandatory=True)
    target_bucket = field(type=unicode, mandatory=True)
    target_key = field(type=unicode, mandatory=True)


@sync_performer
def perform_write_to_s3(dispatcher, intent):
    """
    Create a new object in an existing S3 bucket with the key and content in
    ``intent``.
    """
    client = boto3.client("s3")
    client.put_object(
        Bucket=intent.target_bucket,
        Key=intent.target_key,
        Body=intent.content
    )

# Map intents to performers.
DISPATCHER = ComposedDispatcher([
    TypeDispatcher(
        {
            PackerConfigure: perform_packer_configure,
            PackerBuild: perform_packer_build,
            WriteToS3: perform_write_to_s3,
        }
    ),
    base_dispatcher
])


def _validate_constant(constants, option_value, option_name):
    try:
        constant_value = constants.lookupByValue(option_value)
    except ValueError:
        raise UsageError(
            "The option '--{}' got unsupported value: '{}'. "
            "Must be one of: {}.".format(
                option_name, option_value,
                ', '.join(c.value for c in constants.iterconstants())
            )
        )
    return constant_value


class PublishInstallerImagesOptions(Options):
    """
    Options for uploading Packer-generated image IDs.
    """
    optFlags = [
        ["copy_to_all_regions", None,
         "Copy images to all regions. [default: False]"]
    ]
    optParameters = [
        ["target_bucket", None, DEFAULT_IMAGE_BUCKET,
         "The bucket to upload installer AMI names to.\n", unicode],
        ["build_region", None, DEFAULT_BUILD_REGION.value,
         "A region where the image will be built.\n", unicode],
        ["distribution", None, DEFAULT_DISTRIBUTION,
         "The distribution of operating system to install.\n", unicode],
        ["source_ami", None, DEFAULT_AMI,
         "The distribution of operating system to install.\n", unicode],
        ["template", None, DEFAULT_TEMPLATE,
         "The template to build.\n", unicode],
    ]

    def __init__(self):
        Options.__init__(self)
        self['regions'] = Regions()

    def opt_region(self, value):
        """
        Specify a region to publish the images to. Can be used multiple times.
        """
        region = _validate_constant(
            constants=AWS_REGIONS,
            option_value=value.decode('utf-8'),
            option_name=u'region'
        )
        self['regions'] += [region]

    def postOptions(self):
        self["build_region"] = _validate_constant(
            constants=AWS_REGIONS,
            option_value=self["build_region"],
            option_name=u"build_region"
        )
        self["copy_to_all_regions"] = bool(self["copy_to_all_regions"])
        if self['copy_to_all_regions']:
            if self['regions']:
                raise UsageError(
                    '--copy_to_all_regions and --region '
                    'can not be used together.'
                )
            else:
                self['regions'] = tuple(AWS_REGIONS.iterconstants())


class _PublishInstallerImagesMain(object):
    """
    A container for the main functions of ``publish-installer-images`` with
    attributes to allow overriding the stdout and stderr and the working
    directory used by the constituent Effects.
    """
    def __init__(self, sys_module=None, working_directory=None):
        if sys_module is None:
            sys_module = sys
        self.sys_module = sys_module

        if working_directory is None:
            working_directory = FilePath(mkdtemp())
        self.working_directory = working_directory

    def _parse_options(self, args):
        options = PublishInstallerImagesOptions()

        try:
            options.parseOptions(args)
        except UsageError as e:
            self.sys_module.stderr.write(
                "Usage Error: %s: %s\n" % (
                    self.base_path.basename(), e
                )
            )
            raise SystemExit(1)
        return options

    @do
    def packer_publish(self, reactor, template, options, source_ami):
        # Create configuration directory
        template_path = yield Effect(
            intent=PackerConfigure(
                build_region=options["build_region"],
                publish_regions=options["regions"],
                working_directory=self.working_directory,
                template=template,
                distribution=options["distribution"],
                source_ami=source_ami,
            )
        )
        # Build the Docker images
        ami_map = yield Effect(
            intent=PackerBuild(
                reactor=reactor,
                template=template_path,
            )
        )
        # Publish the regional AMI map to S3
        yield Effect(
            intent=WriteToS3(
                content=json.dumps(thaw(ami_map), encoding="utf-8"),
                target_bucket=options['target_bucket'],
                target_key=template,
            )
        )
        yield do_return(ami_map)

    @do
    def main_effect(self, reactor, options):
        amis = yield self.packer_publish(
            reactor=reactor,
            template=options["template"],
            source_ami=options["source_ami"],
            options=options,
        )
        yield do_return(amis)

    def main(self, reactor, args, base_path, top_level):
        self.reactor = reactor
        self.base_path = base_path
        self.top_level = top_level
        options = self._parse_options(args)
        effect = self.main_effect(reactor, options)
        return async_perform(DISPATCHER, effect)

publish_installer_images_main = _PublishInstallerImagesMain().main

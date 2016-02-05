# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Utilities for cloud resource cleanup.
"""
from datetime import datetime, timedelta
import json
import sys
from uuid import UUID
import yaml

from characteristic import attributes

from dateutil.parser import parse as parse_date
from dateutil.tz import tzutc

from libcloud.compute.providers import get_driver, Provider

from twisted.internet.threads import deferToThread
from twisted.python.log import err
from twisted.python.usage import Options, UsageError

# Marker value defined by ``flocker.testtools.cluster_utils.MARKER``.  This
# should never change and should always identify test-created clusters.
MARKER = 0xAAAAAAAAAAAA


def get_creation_time(node):
    """
    Get the creation time of a libcloud node.

    Rackspace and EC2 store the information in different metadeta.

    :return: The creation time, if available.
    :rtype: datetime or None
    """
    date_string = node.extra.get("created", node.extra.get("launch_time"))
    if date_string is None:
        return None
    else:
        return parse_date(date_string)


def get_rackspace_driver(rackspace):
    """
    Get a libcloud Rackspace driver given some credentials and other
    configuration.
    """
    rackspace = get_driver(Provider.RACKSPACE)(
        rackspace['username'], rackspace['key'],
        region=rackspace['region'],
    )
    return rackspace


def get_ec2_driver(aws):
    """
    Get a libcloud EC2 driver given some credentials and other configuration.
    """
    ec2 = get_driver(Provider.EC2)(
        aws['access_key'], aws['secret_access_token'],
        region=aws['region'],
    )
    return ec2


@attributes(["lag"])
class CleanVolumes(object):
    """
    Destroy volumes that leaked into the cloud from the acceptance and
    functional test suites.
    """
    name = 'clean-volumes'
    description = ['Cleaning', 'volumes']
    descriptionDone = ['Clean', 'volumes']
    haltOnFailure = False
    flunkOnFailure = True

    def start(self):
        config = privateData['acceptance']['config']
        d = deferToThread(self._blocking_clean_volumes, yaml.safe_load(config))
        d.addCallback(self.log)
        d.addErrback(self.failed)

    def _get_cloud_drivers(self, config):
        """
        From the private buildbot configuration, construct a list of all of the
        libcloud drivers where leaked volumes might be found.
        """
        base_ec2 = config["aws"]

        drivers = [
            get_rackspace_driver(config["rackspace"]),
            get_ec2_driver(base_ec2),
        ]

        for extra in config["extra-aws"]:
            extra_driver_config = base_ec2.copy()
            extra_driver_config.update(extra)
            drivers.append(get_ec2_driver(config))
        return drivers

    def _get_cloud_volumes(self, drivers):
        """
        From the given libcloud drivers, look up all existing volumes.
        """
        volumes = []
        for driver in drivers:
            volumes.extend(driver.list_volumes())
        return volumes

    def _get_cluster_id(self, volume):
        """
        Extract the Flocker-specific cluster identifier from the given volume.

        :raise: ``KeyError`` if the given volume is not tagged with a Flocker
            cluster id.
        """
        return _get_tag(volume, 'flocker-cluster-id')

    def _is_test_cluster(self, cluster_id):
        """
        Determine whether or not the given Flocker cluster identifier belongs
        to a cluster created by a test suite run.

        :return: ``True`` if it does, ``False`` if it does not.
        """
        try:
            return UUID(cluster_id).node == MARKER
        except:
            err(None, "Could not parse cluster_id {!r}".format(cluster_id))
            return False

    def _is_test_volume(self, volume):
        """
        Determine whether or not the given volume belongs to a test-created
        Flocker cluster (and is therefore subject to automatic destruction).

        :return: ``True`` if it does, ``False`` if it does not.
        """
        try:
            cluster_id = self._get_cluster_id(volume)
        except KeyError:
            return False
        return self._is_test_cluster(cluster_id)

    def _get_volume_creation_time(self, volume):
        """
        Extract the creation time from an AWS or Rackspace volume.

        libcloud doesn't represent volume creation time uniformly across
        drivers.  Thus this method only works on drivers specifically accounted
        for.
        """
        try:
            # AWS
            return volume.extra['create_time']
        except KeyError:
            # Rackspace.  Timestamps have no timezone indicated.  Manual
            # experimentation indicates timestamps are in UTC (which of course
            # is the only reasonable thing).
            return parse_date(
                volume.extra['created_at']
            ).replace(tzinfo=tzutc())

    def _filter_test_volumes(self, maximum_age, volumes):
        """
        From the given list of volumes, find volumes created by tests which are
        older than the maximum age.

        :param timedelta maximum_age: The oldest a volume may be without being
            considered old enough to include in the result.
        :param list all_volumes: The libcloud volumes representing all the
            volumes we can see on a particular cloud service.

        :rtype: ``VolumeActions``
        """
        now = datetime.now(tz=tzutc())
        destroy = []
        keep = []
        for volume in volumes:
            created = self._get_volume_creation_time(volume)
            if self._is_test_volume(volume) and now - created > maximum_age:
                destroy.append(volume)
            else:
                keep.append(volume)
        return VolumeActions(destroy=destroy, keep=keep)

    def _destroy_cloud_volumes(self, volumes):
        """
        Unconditionally and irrevocably destroy all of the given cloud volumes.
        """
        for volume in volumes:
            try:
                volume.destroy()
            except:
                err(None, "Destroying volume.")

    def _blocking_clean_volumes(self, config):
        """
        Clean up old volumes belonging to test-created Flocker clusters.
        """
        drivers = self._get_cloud_drivers(config)
        volumes = self._get_cloud_volumes(drivers)
        actions = self._filter_test_volumes(self.lag, volumes)
        self._destroy_cloud_volumes(actions.destroy)
        return {
            "destroyed": actions.destroy,
            "kept": actions.keep,
        }

    def _get_volume_region(self, volume):
        """
        Get the name of the region the volume is in.
        """
        return (
            # Rackspace
            getattr(volume.driver, "region", None) or
            # AWS
            getattr(volume.driver, "region_name", None)
        )

    def _describe_volume(self, volume):
        """
        Create a dictionary giving lots of interesting details about a cloud
        volume.
        """
        return {
            'id': volume.id,
            'creation_time': _format_time(
                self._get_volume_creation_time(volume),
            ),
            'provider': volume.driver.name,
            'region': self._get_volume_region(volume),
            # *Stuffed* with non-JSON-encodable goodies.
            'extra': repr(volume.extra),
        }

    def log(self, result):
        """
        Log the results of a cleanup run.

        The log will include volumes that were destroyed and volumes that were
        kept.  If volumes are destroyed, the step is considered to have failed.
        The test suite should have cleaned those volumes up.  This is an
        unfortunate time to be reporting the problem but it's better than never
        reporting it.
        """
        for (kind, volumes) in result.items():
            content = _dumps(
                sorted(
                    list(
                        self._describe_volume(volume) for volume in volumes
                    ), key=lambda description: description['creation_time'],
                )
            )
            self.addCompleteLog(name=kind, text=content)

        if len(result['destroyed']) > 0:
            # We fail if we destroyed any volumes because that means that
            # something is leaking volumes.
            self.finished(FAILURE)
        else:
            self.finished(SUCCESS)


def _dumps(obj):
    """
    JSON encode an object using some visually pleasing formatting.
    """
    return json.dumps(obj, sort_keys=True, indent=4, separators=(',', ': '))


def _format_time(when):
    """
    Format a time to ISO8601 format.  Or if there is no time, just return
    ``None``.
    """
    if when is None:
        return None
    return datetime.isoformat(when)


def _get_tag(volume, tag_name):
    """
    Get a "tag" from an EBS or Rackspace volume.

    libcloud doesn't represent tags uniformly across drivers.  Thus this method
    only works on drivers specifically account for.

    :raise: ``KeyError`` if the tag is not present.
    """
    return volume.extra.get("tags", volume.extra.get("metadata"))[tag_name]


@attributes(["destroy", "keep"])
class VolumeActions(object):
    """
    Represent something to be done to some volumes.

    :ivar destroy: Volumes to destroy.
    :ivar keep: Volumes to keep.
    """


class CleanupCloudResourcesOptions(Options):
    """
    """


def cleanup_cloud_resources_main(reactor, args, base_path, top_level):
    options = CleanupCloudResourcesOptions()

    try:
        options.parseOptions(args)
    except UsageError as e:
        sys.stderr.write(
            "Usage Error: %s: %s\n" % (
                base_path.basename(), e
            )
        )
        raise SystemExit(1)
    return CleanVolumes(lag=timedelta(minutes=30)).start()

"""
Flocker volume manager prototype.

Each flocker instance is configured with a specific pool, which is assumed
to be mounted at /<poolname>.

For simplicity's sake not bothering with UUIDs, you need to make sure names
don't conflict. Volume/branch/tag names should not contain "." because of
hacky implementation details.

Volumes will be exposed in docker containers in folder '/flocker'.
"""

import time
import subprocess
from collections import namedtuple

from twisted.python.usage import Options, UsageError
from twisted.python.filepath import FilePath


def zfs(*arguments):
    """
    Run a 'zfs' command with given arguments, raise on non-0 exit code.

    @return: stdout bytes.
    """
    return subprocess.check_output(["zfs"] + list(arguments))



def docker(*arguments):
    """
    Run a 'docker' comand with given arguments, raise on non-0 exit code.
    """
    subprocess.check_call(["docker"] + list(arguments))



class FlockerVolume(namedtuple("FlockerVolume", "flockerName name")):
    """
    The canonical name of a flocker volume.

    @ivar flockerName: The name of the flocker instance from which the
        volume originates, as L{bytes}.

    @ivar name: The name of the volume, e.g. L{b"myvolume"}.
    """
    def publicName(self, thisFlockerName):
        """
        The command-line name of the volume.

        @param thisFlockerName: Name of current flocker instance.
        """
        if thisFlockerName == self.flockerName:
            return self.name
        else:
            return b"%s/%s" % (self.flockerName, self.name)


    @classmethod
    def fromPublicName(cls, name, thisFlockerName):
        """
        Parse output of L{publicName} into a L{FlockerVolume}.
        """
        if b"/" in name:
            flockerName, volume = name.split(b"/")
        else:
            volume = name
            flockerName = thisFlockerName
        return FlockerVolume(flockerName, volume)



class FlockerBranch(namedtuple("FlockerBranch", "volume name")):
    """
    The canonical name of a flocker volume: <flocker instance>/<volume>/<branch>

    @type volume: L{FlockerVolume}

    @ivar name: The branch subset of the full branch name, e.g. L{b"trunk"}.
    @type name: L{bytes}
    """
    def mountName(self):
        """
        The name of the mountpoint directory.
        """
        return b".".join([self.volume.flockerName, self.volume.name, self.name])


    def datasetName(self, poolName):
        """
        The name of the ZFS dataset for the branch.
        """
        return poolName + b"/" + self.mountName()


    @classmethod
    def fromDatasetName(cls, datasetName):
        """
        Convert ZFS dataset name to FlockerBranch instance.
        """
        flockerName, volumeName, branchName = datasetName.split(b".")
        volume = FlockerVolume(flockerName, volumeName)
        return cls(volume, branchName)


    def publicName(self, thisFlockerName):
        """
        The public (command-line) branch name.

        @param thisFlockerName: Name of current flocker instance.
        """
        return b"%s/%s" % (self.volume.publicName(thisFlockerName), self.name)


    @classmethod
    def fromPublicName(cls, branchName, thisFlockerName):
        """
        Convert public branch name (volume/branch or flocker/volume/branch) to
        FlockerBranch.

        @param thisFlockerName: Name of flocker instance to use for 2-part
           variant branch name, i.e. local branch name.
        """
        volumeName, branchName = branchName.rsplit(b"/", 1)
        return cls(FlockerVolume.fromPublicName(volumeName, thisFlockerName),
                   branchName)



class FlockerTag(namedtuple("FlockerTag", "volume name")):
    """
    The canonical name of a flocker tag: <tag>@<flocker instance>/<volume>

    @type volume: L{FlockerVolume}

    @ivar name: The tag subset of the full branch name, e.g. L{b"mytag"}.
    @type name: L{bytes}
    """
    def snapshotName(self, branchName, poolName):
        """
        The name of the ZFS snapshot for the tag.
        """
        branch = FlockerBranch(self.volume, branchName)
        return branch.datasetName(poolName) + b"@flocker-tag-" + self.name


    def publicName(self, thisFlockerName):
        """
        The command-line name of the tag.

        @param thisFlockerName: Name of current flocker instance.
        """
        return b"%s@%s" % (self.name, self.volume.publicName(thisFlockerName))


    @classmethod
    def fromPublicName(cls, name, thisFlockerName):
        """
        Parse output of L{publicName} into a L{FlockerTag}.
        """
        tag, volumeName = name.split(b"@")
        return FlockerTag(
            FlockerVolume.fromPublicName(volumeName, thisFlockerName), tag)



class Flocker(object):
    """
    Flocker volume manager.
    """
    def __init__(self, poolName):
        self.poolName = poolName
        self.mountRoot = FilePath(b"/").child(poolName)
        # Re-use pool name as name for this Flocker instance:
        self.flockerName = poolName


    def _exposeToDocker(self, branch):
        """
        Expose a branch to Docker.

        @type branch: L{FlockerBranch}
        """
        mountPath = self.mountRoot.child(branch.mountName()).path
        containerName = b"flocker--%s--%s" % (branch.volume.name, branch.name)
        docker(b"run",
               b"--name", containerName,
               b"-v", mountPath + b":/flocker:rw",
               b"busybox", b"true")
        print("You can access this volume by adding '--volumes-from %s' to "
              "'docker run'" % (containerName,))


    def createVolume(self, volumeName):
        """
        Create a new local volume with the given name, e.g. C{b"myvolume"}
        """
        trunk = FlockerBranch(FlockerVolume(self.flockerName, volumeName),
                              b"trunk")
        zfs(b"create", trunk.datasetName(self.poolName))
        self._exposeToDocker(trunk)


    def listVolumes(self):
        """
        Return list of all volumes.
        """
        result = set()
        for branch in self._allBranches():
            result.add(branch.volume.publicName(self.flockerName))
        return result


    def _createBranchFromSnapshotName(self, newBranch, snapshotName):
        """
        @type newBranch: L{FlockerBranch}
        @param snapshotName: L{bytes}, name of ZFS snapshot.
        """
        zfs(b"clone", snapshotName, newBranch.datasetName(self.poolName))
        self._exposeToDocker(newBranch)


    def branchOffBranch(self, newBranch, fromBranch):
        """
        @type newBranch: L{FlockerBranch}
        @type fromBranch: L{FlockerBranch}
        """
        if newBranch.volume.name != fromBranch.volume.name:
            raise ValueError("Can't create branches across volumes")
        if newBranch.volume.flockerName != self.flockerName:
            raise ValueError("Can't create branches on remote volumes")
        snapshotName = b"%s@%s" % (fromBranch.datasetName(self.poolName),
                                   newBranch.mountName())
        zfs(b"snapshot", snapshotName)
        self._createBranchFromSnapshotName(newBranch, snapshotName)


    def _snapshotsForBranch(self, branch):
        """
        Return list of ZFS snapshots for a branch, sorted by ascending creation
        time.

        @param branch: L{FlockerBranch}
        """
        return zfs(b"list", b"-H", b"-o", b"name", b"-r",
                   b"-t", b"snapshot", "-s", "creation",
                   branch.datasetName(self.poolName)).splitlines()


    def branchOffTag(self, newBranch, fromTag):
        """
        @type newBranch: L{FlockerBranch}
        @type fromTag: L{FlockerTag}
        """
        if newBranch.volume.name != fromTag.volume.name:
            raise ValueError("Can't create branches across volumes")
        if newBranch.volume.flockerName != self.flockerName:
            raise ValueError("Can't create branches on remote volumes")
        snapshot = None
        for branch in self._branchesForVolume(fromTag.volume):
            for line in self._snapshotsForBranch(branch):
                dataset, snapshotName = line.split(b"@")
                if snapshotName == b"flocker-tag-" + fromTag.name:
                    snapshot = line
                    break

        if snapshot is None:
            raise ValueError("Can't find tag.")
        self._createBranchFromSnapshotName(newBranch, snapshot)


    def _allBranches(self):
        """
        Return list of all L{FlockerBranch} instances in this instance.
        """
        result = []
        for dataset in zfs(b"list", b"-H", b"-o", "name", b"-d", b"1",
                              self.poolName).splitlines():
            if b"/" not in dataset:
                continue
            branchName = dataset.split(b"/", 1)[1]
            if b"." not in branchName:
                # Some junk, not something we're managing:
                continue
            branch = FlockerBranch.fromDatasetName(branchName)
            result.append(branch)
        return result


    def _branchesForVolume(self, volume):
        """
        Return list of all L{FlockerBranch} instances for given volume.

        @param volume: L{FlockerVolume}
        """
        return [b for b in self._allBranches() if b.volume == volume]


    def listBranches(self, volume):
        """
        Return list of all branch names for given volume.
        """
        return [branch.publicName(self.flockerName)
                for branch in self._branchesForVolume(volume)]


    def createTag(self, branch, tagName):
        """
        Create a tag.
        """
        if branch.volume.flockerName != self.flockerName:
            raise ValueError("Can only tag local branches")
        tag = FlockerTag(branch.volume, tagName)
        zfs(b"snapshot", tag.snapshotName(branch.name, self.poolName))


    def listTags(self, volume):
        """
        Return list of all tags.
        """
        result = []
        for branch in self._branchesForVolume(volume):
            for line in self._snapshotsForBranch(branch):
                dataset, snapshotName = line.split(b"@")
                if snapshotName.startswith(b"flocker-tag-"):
                    tag = FlockerTag(
                        branch.volume,  snapshotName[len(b"flocker-tag-"):])
                    result.append(tag.publicName(self.flockerName))
        return result


    def pushBranch(self, destination, branch):
        """
        Push a branch to another Flocker instance.

        @param destination: A L{Flocker} pointing at another pool.

        @param branch: The L{FlockerBranch} to push.
        """
        if branch.volume.flockerName != self.flockerName:
            raise ValueError("Can only push local branches")

        originDataset = branch.datasetName(self.poolName)

        destinationDataset = branch.datasetName(destination.poolName)
        destinationExists = branch in destination._branchesForVolume(
            branch.volume)

        # Find most recent snapshot that got sent:
        mostRecent = None
        if destinationExists:
            destinationSnapshots = set([
                snapshot.split(b'@')[1] for snapshot
                in destination._snapshotsForBranch(branch)])
            localSnapshots = self._snapshotsForBranch(branch)
            for snapshot in reversed(localSnapshots):
                snapshot = snapshot.split(b'@')[1]
                if snapshot in destinationSnapshots:
                    mostRecent = snapshot
                    break

        # Take a new snapshot:
        snapshotName = b"%s" % (time.time(),)
        newSnapshot = b"%s@%s" % (originDataset, snapshotName)
        zfs(b"snapshot", newSnapshot)

        # Send the difference between most recently pushed and new snapshot:
        initial = b""
        if mostRecent is not None:
            initial = b"-i %s@%s" % (originDataset, mostRecent)
        subprocess.check_call("zfs send %s %s | zfs recv %s@%s" %
                              (initial, newSnapshot, destinationDataset, snapshotName),
                              shell=True)
        zfs(b"set", b"mountpoint=none", destinationDataset)



class CreateOptions(Options):
    """
    Create a volume.
    """
    def parseArgs(self, name):
        self.name = name


    def run(self, flocker):
        flocker.createVolume(self.name)



class ListVolumesOptions(Options):
    """
    List volumes.
    """
    def run(self, flocker):
        for name in flocker.listVolumes():
            print name



class BranchOptions(Options):
    """
    Create a branch.
    """
    optParameters = [
        ["tag", None, None, "The tag to branch off of"],
        ["branch", None, None, "The branch to branch off of"],
    ]


    def parseArgs(self, newBranchName):
        self.newBranchName = newBranchName


    def postOptions(self):
        if self["tag"] is not None and self["branch"] is not None:
            raise UsageError("Only one of 'tag' and 'branch' should be chosen")


    def run(self, flocker):
        destinationBranch = FlockerBranch.fromPublicName(
            self.newBranchName, flocker.flockerName)
        if self["branch"] is not None:
            fromBranch = FlockerBranch.fromPublicName(
                self["branch"], flocker.flockerName)
            flocker.branchOffBranch(destinationBranch, fromBranch)
        else:
            fromTag = FlockerTag.fromPublicName(self["tag"], flocker.flockerName)
            flocker.branchOffTag(destinationBranch, fromTag)



class ListBranchesOptions(Options):
    """
    List branches.
    """
    def parseArgs(self, name):
        self.name = name


    def run(self, flocker):
        volume = FlockerVolume.fromPublicName(self.name, flocker.flockerName)
        for name in flocker.listBranches(volume):
            print name



class TagOptions(Options):
    """
    Create a tag.
    """
    optParameters = [
        ["branch", None, None, "The branch to tag off of"],
    ]


    def parseArgs(self, name):
        self.name = name


    def postOptions(self):
        if self["branch"] is None:
            raise UsageError("'branch' is required")


    def run(self, flocker):
        fromBranch = FlockerBranch.fromPublicName(
            self["branch"], flocker.flockerName)
        flocker.createTag(fromBranch, self.name)



class ListTagsOptions(Options):
    """
    List tags.
    """
    def parseArgs(self, name):
        self.name = name


    def run(self, flocker):
        volume = FlockerVolume.fromPublicName(self.name, flocker.flockerName)
        for name in flocker.listTags(volume):
            print name



class PushBranchOptions(Options):
    """
    Push a branch to another pool.
    """
    optParameters = [
        ["destination", "d", None, "The destination pool for the branch"],
    ]


    def parseArgs(self, name):
        self.name = name


    def run(self, flocker):
        if self["destination"] is None:
            raise UsageError("'destination' is required")
        destination = Flocker(self["destination"])
        branch = FlockerBranch.fromPublicName(self.name, flocker.flockerName)
        flocker.pushBranch(destination, branch)



class FlockerOptions(Options):
    """
    Flocker volume manager.
    """
    optParameters = [
        ["pool", "p", None, "The name of the pool to use"],
        ]

    subCommands = [
        ["volume", None, CreateOptions, "Create a volume and its default trunk branch"],
        ["list-volumes", None, ListVolumesOptions, "List volumes"],
        ["branch", None, BranchOptions, "Create a branch"],
        ["list-branches", None, ListBranchesOptions, "List branches"],
        #["delete-branch", None, DeleteBranchOptions, "Delete a branch"],
        ["tag", None, TagOptions, "Create a tag"],
        ["list-tags", None, ListTagsOptions, "List tags"],
        ["push-branch", None, PushBranchOptions, "Push a branch to another pool"],
        ]


    def postOptions(self):
        if self.subCommand is None:
            return self.opt_help()
        if self["pool"] is None:
            raise UsageError("pool is required")
        self.subOptions.run(Flocker(self["pool"]))



if __name__ == '__main__':
    FlockerOptions().parseOptions()

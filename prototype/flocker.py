"""
Flocker volume manager prototype.

Each flocker instance is configured with a specific pool, which is assumed
to be mounted at /<poolname>.

For simplicity's sake not bothering with UUIDs, you need to make sure names
don't conflict. Volume/branch/tag names should not contain "." because of
hacky implementation details.

Volumes will be exposed in docker containers in folder '/flocker'.
"""

import subprocess
from collections import namedtuple

from twisted.python.usage import Options, UsageError
from twisted.python.filepath import FilePath


def zfs(*arguments):
    """
    Run a 'zfs' command with given arguments, raise on non-0 exit code.

    @return: stdout bytes.
    """
    subprocess.check_call(["zfs"] + list(arguments))



def docker(*arguments):
    """
    Run a 'docker' comand with given arguments, raise on non-0 exit code.
    """
    subprocess.check_call(["docker"] + list(arguments))



class FlockerBranch(namedtuple("FlockerBranch", "flockerName volume branch")):
    """
    The canonical name of a flocker volume: <flocker instance>/<volume>/<branch>
    """
    def mountName(self):
        """
        The name of the mountpoint directory.
        """
        return b".".join([self.flockerName, self.volume, self.branch])


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
        return cls(*datasetName.split(b"."))


    @classmethod
    def fromBranchName(cls, branchName, thisFlockerName):
        """
        Convert branch name (volume/branch or flocker/volume/branch) to
        FlockerBranch.

        @param thisFlockerName: Name of flocker instance to use for 2-part
           variant branch name, i.e. local branch name.
        """
        parts = branchName.split(b"/")
        if len(parts) == 2:
            parts.insert(0, thisFlockerName)
        return cls(*parts)



class FlockerTag(namedtuple("FlockerTag", "flockerName volume tag")):
    """
    The canonical name of a flocker tag: <tag>@<flocker instance>/<volume>
    """
    def snapshotName(self, branchName, poolName):
        """
        The name of the ZFS snapshot for the tag.
        """
        branch = FlockerBranch(self.flockerName, self.volume, branchName)
        return branch.datasetName(poolName) + b"@flocker-tag-" + self.tag



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
        containerName = b"flocker--%s--%s" % (branch.volume, branch.branch)
        docker(b"run",
               b"--name", containerName,
               b"-v", mountPath + b":/flocker:rw",
               b"busybox", b"true")
        print("You can access this volume by adding '--volumes-from %s' to "
              "'docker run'" % (containerName,))


    def createVolume(self, volumeName):
        """
        Create a new volume with given name.
        """
        trunk = FlockerBranch(self.flockerName, volumeName, b"trunk")
        zfs(b"create", trunk.datasetName(self.poolName))
        self._exposeToDocker(trunk)


    def listVolumes(self):
        """
        Return list of all volumes.
        """
        result = set()
        for branchName in self.mountRoot.listdir():
            if b"." not in branchName:
                # Some junk, not something we're managing:
                continue
            branch = FlockerBranch.fromDatasetName(branchName)
            result.add(branch.volume)
        return result


    def branchOffBranch(self, newBranch, fromBranch):
        """
        @type newBranch: L{FlockerBranch}
        @type fromBranch: L{FlockerBranch}
        """
        if newBranch.volume != fromBranch.volume:
            raise ValueError("Can't create branches across volumes")
        snapshotName = b"%s@%s" % (fromBranch.datasetName(self.poolName),
                                   newBranch.branch)
        zfs(b"snapshot", snapshotName)
        zfs(b"clone", snapshotName, newBranch.datasetName(self.poolName))
        self._exposeToDocker(newBranch)


    def _branchesForVolume(self, volumeName):
        """
        Return list of all L{FlockerBranch} instances for given volume.
        """
        result = []
        for branchName in self.mountRoot.listdir():
            if b"." not in branchName:
                # Some junk, not something we're managing:
                continue
            branch = FlockerBranch.fromDatasetName(branchName)
            if branch.volume != volumeName:
                continue
            result.append(branch)
        return result


    def listBranches(self, volumeName):
        """
        Return list of all branch names for given volume.
        """
        result = []
        for branch in self._branchesForVolumes(volumeName):
            if branch.flockerName == self.flockerName:
                result.append(b"%s/%s" % (branch.volume, branch.branch))
            else:
                result.append(b"/".join(branch))
        return result


    def createTag(self, branch, tagName):
        """
        Create a tag.
        """
        if branch.flockerName != self.flockerName:
            raise ValueError("Can only tag local branches")
        tag = FlockerTag(branch.flockerName, branch.volume, tagName)
        zfs(b"snapshot", tag.snapshotName(branch.branch, self.poolName))


    def listTags(self, volumeName):
        """
        Return list of all tags.
        """
        result = []
        for branch in self._branchesForVolumes(volumeName):
            for line in zfs(... list snapshots ...):
                if istag:
                    result.append(...)
        return result



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
        if self["branch"] is not None:
            fromBranch = FlockerBranch.fromBranchName(
                self["branch"], flocker.flockerName)
            destinationBranch = FlockerBranch.fromBranchName(
                self.newBranchName, flocker.flockerName)
            flocker.branchOffBranch(destinationBranch, fromBranch)
        else:
            raise NotImplementedError("tags don't work yet")



class ListBranchesOptions(Options):
    """
    List branches.
    """
    def parseArgs(self, name):
        self.name = name


    def run(self, flocker):
        for name in flocker.listBranches(self.name):
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
        fromBranch = FlockerBranch.fromBranchName(
            self["branch"], flocker.flockerName)
        flocker.createTag(fromBranch, self.name)



class ListTagsOptions(Options):
    """
    List tags.
    """
    def parseArgs(self, name):
        self.name = name


    def run(self, flocker):
        for name in flocker.listTags(self.name):
            print name



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
        #["send", None, SendOptions, "Like push, except writing to stdout"],
        #["receive", None, ReceiveOptions, "Read in the output of send - bit like pull"],
        ]


    def postOptions(self):
        if self.subCommand is None:
            return self.opt_help()
        if self["pool"] is None:
            raise UsageError("pool is required")
        self.subOptions.run(Flocker(self["pool"]))



if __name__ == '__main__':
    FlockerOptions().parseOptions()

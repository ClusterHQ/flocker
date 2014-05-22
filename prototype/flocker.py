"""
Flocker volume manager prototype.

Each flocker instance is configured with a specific pool, which is assumed
to be mounted at /<poolname>.

For simplicity's sake not bothering with UUIDs, you need to make sure names
don't conflict. Volume/branch/tag names should not contain "." because of
hacky implementation details.
"""

import subprocess
from collections import namedtuple

from twisted.python.usage import Options, UsageError
from twisted.python.filepath import FilePath


def zfs(*arguments):
    """
    Run a 'zfs' command with given arguments, raise on non-0 exit code.
    """
    subprocess.check_call(["zfs"] + list(arguments))



class FlockerBranch(namedtuple("FlockerBranch", "flockerName volume branch")):
    @property
    def datasetName(self):
        """
        The name of the ZFS dataset for the branch.
        """
        return b".".join([self.flockerName, self.volume, self.branch])


    @classmethod
    def fromDatasetName(cls, datasetName):
        """
        Convert ZFS dataset name to FlockerBranch instance.
        """
        return cls(*datasetName.split(b"."))



class Flocker(object):
    """
    Flocker volume manager.
    """
    def __init__(self, poolName):
        self.poolName = poolName
        self.mountRoot = FilePath(b"/").child(poolName)
        # Re-use pool name as name for this Flocker instance:
        self.flockerName = poolName


    def createVolume(self, volumeName):
        """
        Create a new volume with given name.
        """
        trunk = FlockerBranch(self.flockerName, volumeName, b"trunk").datasetName
        zfs(b"create", b"%s/%s" % (self.poolName, trunk))


    def listVolumes(self):
        """
        Return list of all volumes.
        """
        result = []
        for branchName in self.mountRoot.listdir():
            if b"." not in branchName:
                # Some junk, not something we're managing:
                continue
            branch = FlockerBranch.fromDatasetName(branchName)
            if branch.flockerName == self.flockerName:
                result.append(b"%s/%s" % (branch.volume, branch.branch))
            else:
                result.append(b"/".join(branch))
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
    def parseArgs(self, name):
        self.name = name


    def run(self, flocker):
        pass



class ListBranchesOptions(Options):
    """
    List branches
    """
    def parseArgs(self, name):
        self.name = name


    def run(self, flocker):
        pass



class TagOptions(Options):
    """
    Create a tag.
    """
    def parseArgs(self, name):
        self.name = name


    def run(self, flocker):
        pass



class ListTagsOptions(Options):
    """
    List tags.
    """
    def parseArgs(self, name):
        self.name = name


    def run(self, flocker):
        pass



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

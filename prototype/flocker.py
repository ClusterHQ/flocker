"""
Flocker volume manager prototype.

Each flocker instance is configured with a specific pool, which is assumed
to be mounted at /<poolname>.

For simplicity's sake not bothering with UUIDs, you need to make sure names
don't conflict.

"""

from twisted.python.usage import Options



class CreateOptions(Options):
    """
    Create a volume.
    """
    def parseArgs(self, name):
        self.name = name


    def postOptions(self):
        pass



class ListVolumesOptions(Options):
    """
    List volumes.
    """
    def postOptions(self):
        pass



class BranchOptions(Options):
    """
    Create a branch.
    """
    def parseArgs(self, name):
        self.name = name


    def postOptions(self):
        pass



class ListBranchesOptions(Options):
    """
    List branches
    """
    def parseArgs(self, name):
        self.name = name


    def postOptions(self):
        pass



class TagOptions(Options):
    """
    Create a tag.
    """
    def parseArgs(self, name):
        self.name = name


    def postOptions(self):
        pass



class ListTagsOptions(Options):
    """
    List tags.
    """
    def parseArgs(self, name):
        self.name = name

    def postOptions(self):
        pass



class FlockerOptions(Options):
    """
    Flocker volume manager.
    """
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



if __name__ == '__main__':
    FlockerOptions().parseOptions()

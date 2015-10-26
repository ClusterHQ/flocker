"""
Store information about relationships between configuration and state.
"""


class BlockDeviceOwnership(CheckedPMap):
    """
    Map dataset_id <-> blockdevice_id.
    """


class Registry(object):
    """
    XXX Wraps same on-disk persistence mechanism as _persistence.py, but
    stores different information.
    """

    def record_ownership(self, dataset_id, blockdevice_id):
        """
        Record that blockdevice_id is the relevant one for given dataset_id.

        Once a record is made no other entry can overwrite the existing
        one; the relationship is hardcoded and permanent. XXX this may
        interact badly with deletion of dataset where dataset_id is
        auto-generated from name, e.g. flocker-deploy or Docker
        plugin. That is pre-existing issue, though.

        XXX having IBlockDeviceAPI specific method is kinda bogus. Some
        sort of generic method for storing data moving forward?
        """
        # Check persisted value, if not already set override and save to
        # disk, otherwise raise error.

    def get_ownership(self):
        """
        Return ownership information, in class suitable for transmitting over
        AMP, i.e. ``BlockDeviceOwnership``

        XXX having IBlockDeviceAPI specific method is kinda bogus. Some
        sort of generic method for storing data moving forward?
        """

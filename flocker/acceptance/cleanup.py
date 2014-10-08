# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Cleanup after acceptance testing.

Invoke as "python -m acceptance.cleanup"
"""
if __name__ == "__main__":
    from acceptance.cleanup import remove_containers
    remove_containers()

def remove_containers():
    """
    Remove docker containers used for acceptance testing.
    """

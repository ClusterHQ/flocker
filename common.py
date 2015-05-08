import yaml
import time
from libcloud.compute.providers import get_driver, Provider
from twisted.python.filepath import FilePath

aws_config = yaml.safe_load(open("aws_config.yml"))['aws']

driver = get_driver(Provider.EC2)(
    key=aws_config['access_key'],
    secret=aws_config['secret_access_token'],
    region=aws_config['region'])


def wait_for_image(image):
    """
    Wait for an image to be available.
    """
    while True:
        try:
            while driver.get_image(image.id).extra['state'] != 'available':
                time.sleep(1)
            else:
                return
        except IndexError:
            time.sleep(1)
        except:
            raise


def load_manifest(name):
    """
    Load a manifest describing a set of images.

    :return: A tuple of a FilePath for the context of the manifest,
        and a dictionary with the manifest.
    """
    base = FilePath(__file__).sibling(name)
    manifest = yaml.load(base.child('manifest.yml').getContent())
    return base, manifest

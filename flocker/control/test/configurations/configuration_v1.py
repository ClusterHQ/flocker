# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

# Generate a v1 configuration.
# Commit Hash: 7bd476e2fdc7353018ff1fc446b9b4c76e7c7c17

from json import dumps, JSONEncoder
from pyrsistent import PRecord, PVector, PMap, PSet
from uuid import UUID, uuid4

from twisted.python.filepath import FilePath

from flocker.control._model import (
    Deployment, Dataset, Manifestation,
    Node, Application, DockerImage, AttachedVolume
)

_CLASS_MARKER = u"$__class__$"

DATASET = Dataset(dataset_id=unicode(uuid4()),
                  metadata={u"name": u"myapp"})
MANIFESTATION = Manifestation(dataset=DATASET, primary=True)
TEST_DEPLOYMENT = Deployment(
    nodes=[Node(uuid=uuid4(),
                applications=[
                    Application(
                        name=u'myapp',
                        image=DockerImage.from_string(u'postgresql:7.6'),
                        volume=AttachedVolume(
                            manifestation=MANIFESTATION,
                            mountpoint=FilePath(b"/xxx/yyy"))
                    )],
                manifestations={DATASET.dataset_id: MANIFESTATION})])


class _ConfigurationEncoder(JSONEncoder):
    """
    JSON encoder that can encode the configuration model.
    """
    def default(self, obj):
        if isinstance(obj, PRecord):
            result = dict(obj)
            result[_CLASS_MARKER] = obj.__class__.__name__
            return result
        elif isinstance(obj, PMap):
            return {_CLASS_MARKER: u"PMap", u"values": dict(obj).items()}
        elif isinstance(obj, (PSet, PVector, set)):
            return list(obj)
        elif isinstance(obj, FilePath):
            return {_CLASS_MARKER: u"FilePath",
                    u"path": obj.path.decode("utf-8")}
        elif isinstance(obj, UUID):
            return {_CLASS_MARKER: u"UUID",
                    "hex": unicode(obj)}
        return JSONEncoder.default(self, obj)


def wire_encode(obj):
    """
    Encode the given configuration object into bytes.

    :param obj: An object from the configuration model, e.g. ``Deployment``.
    :return bytes: Encoded object.
    """
    return dumps(obj, cls=_ConfigurationEncoder)


def generate_v1_config():
    return wire_encode(TEST_DEPLOYMENT)

if __name__ == "__main__":
    print generate_v1_config()

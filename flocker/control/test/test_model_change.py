# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Whenever the configuration model changes we need to write code to
upgrade the on-disk format from previous releases. This module will
automatically detect such changes by failing a test, ensuring that upgrade
code is always implemented when necessary.
"""

from json import loads, dumps
from subprocess import check_output

from pyrsistent import PRecord

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath
from twisted.python.reflect import qual as fqpn

from .._model import Deployment

PERSISTED_MODEL = FilePath(__file__).sibling(b"persisted_model.json")

# The class at the root of the configuration tree. This may need to be
# changed if the configuration's root class changes.
ROOT_CLASS = Deployment


def generate_model():
    """
    Generate a data-structure that represents the current configuration
    model.

    Changes to output may require regenerating the persisted version
    on-disk.
    """
    classes_result = {}
    result = {u"root": fqpn(ROOT_CLASS),
              u"classes": classes_result}
    classes = {ROOT_CLASS}
    while classes:
        klass = classes.pop()
        klass_name = fqpn(klass)
        if klass_name in classes_result:
            continue
        record = None
        if issubclass(klass, PRecord):
            record = {u"category": u"record",
                      u"fields": {}}
            # XXX file issue with pyrsistent to add introspection API if I
            # can't find anything in docs:
            for name, field in klass._precord_fields.items():
                record[u"fields"][name] = list(fqpn(cls) for cls in field.type)
                for cls in field.type:
                    classes.add(cls)
        # XXX CheckedPMap and friends
        classes_result[klass_name] = record
    return result


# XXX generate_model() is probably sufficiently important to get right that is should also have tests.


def persist_model():
    """
    Store the current model to disk.

    We also store the git hash of current checkout, so it's clear what
    version of code was used to generate the model.
    """
    git_hash = check_output(
        [b"git", b"show", b"--format=%H"]).strip()
    model = generate_model()
    PERSISTED_MODEL.setContent(dumps({
        u"git_hash": git_hash, u"model": model,
    }))
    print("Persisted model for git hash {}.".format(git_hash))


class ConfigurationModelChanged(SynchronousTestCase):
    """
    Detect when the configuration model has changed.
    """
    def test_model_changed(self):
        """
        If the configuration model changes this test will fail.

        This does not indicate a bug. Rather, it indicates that you should
        implement upgrade code for the on-disk configuration. Once you are
        confident it is possible to upgrade from older versions of Flocker
        to the new version of the code you have introduced, you can update
        this test by running:

            $ python -m flocker.control.test.test_model_change

        And then committing the resulting changes to git.
        """
        current_model = generate_model()
        previous_model = loads(PERSISTED_MODEL.getContent())[u"model"]
        self.assertEqual(current_model, previous_model,
                         self.test_model_changed.__doc__)


if __name__ == '__main__':
    persist_model()

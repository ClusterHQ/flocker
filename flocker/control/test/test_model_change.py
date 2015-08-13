# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Whenever the configuration model changes we need to write code to
upgrade the on-disk format from previous releases. This module will
automatically detect such changes by failing a test, ensuring that upgrade
code is always implemented when necessary.
"""

from json import loads, dumps
from subprocess import check_output

from pyrsistent import (
    PRecord, PClass, CheckedPSet, CheckedPVector, CheckedPMap, field,
)

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath
from twisted.python.reflect import qual as fqpn

from .._model import Deployment

PERSISTED_MODEL = FilePath(__file__).sibling(b"persisted_model.json")

# The class at the root of the configuration tree. This may need to be
# changed if the configuration's root class changes.
ROOT_CLASS = Deployment


def generate_model(root_class=ROOT_CLASS):
    """
    Generate a data-structure that represents the current configuration
    model.

    Changes to output may require regenerating the persisted version
    on-disk.

    This should switch to Pyrsistent's introspection API once it exists:
    https://github.com/tobgu/pyrsistent/issues/47
    """
    classes_result = {}
    result = {u"root": fqpn(root_class),
              u"classes": classes_result}
    classes = {root_class}
    while classes:
        klass = classes.pop()
        klass_name = fqpn(klass)
        if klass_name in classes_result:
            continue
        record = None
        if issubclass(klass, (PRecord, PClass)):
            if issubclass(klass, PRecord):
                attr_name = "_precord_fields"
            else:
                attr_name = "_pclass_fields"
            record = {u"category": u"record",
                      u"fields": {}}
            for name, field_info in getattr(klass, attr_name).items():
                record[u"fields"][name] = list(
                    fqpn(cls) for cls in field_info.type)
                for cls in field_info.type:
                    classes.add(cls)
        elif issubclass(klass, CheckedPMap):
            record = {
                u"category": u"map",
                u"fields": {
                    u"key": list(
                        fqpn(cls) for cls in klass._checked_key_types),
                    u"value": list(
                        fqpn(cls) for cls in klass._checked_value_types)}}
            for cls in klass._checked_key_types + klass._checked_value_types:
                classes.add(cls)
        elif issubclass(klass, (CheckedPSet, CheckedPVector)):
            category = u"set" if issubclass(klass, CheckedPSet) else u"list"
            record = {
                u"category": category,
                u"type": list(fqpn(cls) for cls in klass._checked_types),
            }
            for cls in klass._checked_types:
                classes.add(cls)
        classes_result[klass_name] = record
    return result


class Subtype(PRecord):
    """
    A sub-type used in ``GenerateModelTests``.
    """


class ChangedSubtype(PRecord):
    """
    A changed variant of ``Subtype``.
    """
    x = field()
ChangedSubtype.__name__ = "Subtype"


class GenerateModelTests(SynchronousTestCase):
    """
    Ensure that ``generate_model`` actually catches changes to the model.
    """
    def assert_catches_changes(self, original_class, changed_class):
        """
        Assert that ``generate_model`` changes its output when the underlying
        class has changed.

        :param original_class: Class in initial state.
        :param changed_class: Class in changed state.
        """
        original_model = generate_model(original_class)
        changed_model = generate_model(changed_class)
        # Make sure result is JSON serializable:
        dumps(original_model)
        dumps(changed_model)
        self.assertEqual(
            # Changes result in a difference:
            (original_model != changed_model,
             # No changes result in same output:
             original_model == generate_model(original_class),
             changed_model == generate_model(changed_class)),
            (True, True, True))

    def test_different_class(self):
        """
        If a different root class is given the output changes.
        """
        class Original(PClass):
            pass

        class Different(PClass):
            pass

        self.assert_catches_changes(Original, Different)

    def test_precord_new_field(self):
        """
        If a new field is added to a ``PRecord`` the output changes.
        """
        class Original(PRecord):
            pass

        class Different(PRecord):
            x = field()
        Different.__name__ = "Original"

        self.assert_catches_changes(Original, Different)

    def test_precord_removed_field(self):
        """
        If an existing field is removed from a ``PRecord`` the output
        changes.
        """
        class Original(PRecord):
            x = field()
            y = field()

        class Different(PRecord):
            x = field()
        Different.__name__ = "Original"

        self.assert_catches_changes(Original, Different)

    def test_precord_field_changed_types(self):
        """
        If an existing field has its type changed in a ``PRecord`` the output
        changes.
        """
        class Original(PRecord):
            x = field()

        class Different(PRecord):
            x = field(type=int)
        Different.__name__ = "Original"

        self.assert_catches_changes(Original, Different)

    def test_precord_field_type_changed(self):
        """
        If the an existing field in a ``PRecord`` has the same type, but the
        type changed somehow, the output changes.
        """
        class Original(PRecord):
            x = field(type=Subtype)

        class Different(PRecord):
            x = field(type=ChangedSubtype)
        Different.__name__ = "Original"

        self.assert_catches_changes(Original, Different)

    def test_pclass_new_field(self):
        """
        If a new field is added to a ``PClass`` the output changes.
        """
        class Original(PClass):
            pass

        class Different(PClass):
            x = field()
        Different.__name__ = "Original"

        self.assert_catches_changes(Original, Different)

    def test_pclass_removed_field(self):
        """
        If an existing field is removed from a ``PClass`` the output
        changes.
        """
        class Original(PClass):
            x = field()
            y = field()

        class Different(PClass):
            x = field()
        Different.__name__ = "Original"

        self.assert_catches_changes(Original, Different)

    def test_pclass_field_changed_types(self):
        """
        If an existing field has its type changed in a ``PClass`` the output
        changes.
        """
        class Original(PClass):
            x = field()

        class Different(PClass):
            x = field(type=int)
        Different.__name__ = "Original"

        self.assert_catches_changes(Original, Different)

    def test_pclass_field_type_changed(self):
        """
        If the an existing field in a ``PClass`` has the same type, but the
        type changed somehow, the output changes.
        """
        class Subtype(PClass):
            pass

        class ChangedSubtype(PClass):
            x = field()
        ChangedSubtype.__name__ = "Subtype"

        class Original(PClass):
            x = field(type=Subtype)

        class Different(PClass):
            x = field(type=ChangedSubtype)
        Different.__name__ = "Original"

        self.assert_catches_changes(Original, Different)

    def test_pmap_key_new_type(self):
        """
        If the type of the key of a ``PMap`` changes the output changes.
        """
        class Original(CheckedPMap):
            __key_type__ = int
            __value_type__ = int

        class Different(CheckedPMap):
            __key_type__ = str
            __value_type__ = int
        Different.__name__ = "Original"

        self.assert_catches_changes(Original, Different)

    def test_pmap_value_new_type(self):
        """
        If the type of the value of a ``PMap`` changes the output changes.
        """
        class Original(CheckedPMap):
            __key_type__ = int
            __value_type__ = int

        class Different(CheckedPMap):
            __key_type__ = int
            __value_type__ = str
        Different.__name__ = "Original"

        self.assert_catches_changes(Original, Different)

    def test_pmap_key_type_changed(self):
        """
        If the type of the key of a ``PMap`` is the same, but it has
        internally changed then the output changes.
        """
        class Original(CheckedPMap):
            __key_type__ = Subtype
            __value_type__ = int

        class Different(CheckedPMap):
            __key_type__ = ChangedSubtype
            __value_type__ = int
        Different.__name__ = "Original"

        self.assert_catches_changes(Original, Different)

    def test_pmap_value_type_changed(self):
        """
        If the type of the value of a ``PMap`` is the same, but it has
        internally changed then the output changes.
        """
        class Original(CheckedPMap):
            __key_type__ = int
            __value_type__ = Subtype

        class Different(CheckedPMap):
            __key_type__ = int
            __value_type__ = ChangedSubtype
        Different.__name__ = "Original"

        self.assert_catches_changes(Original, Different)

    def test_pset_value_new_type(self):
        """
        If the type of the value of a ``PSet`` changes the output changes.
        """
        class Original(CheckedPSet):
            __type__ = int

        class Different(CheckedPSet):
            __type__ = str
        Different.__name__ = "Original"

        self.assert_catches_changes(Original, Different)

    def test_pset_value_type_changed(self):
        """
        If the type of the value of a ``PSet`` is the same, but it has
        internally changed then the output changes.
        """
        class Original(CheckedPSet):
            __type__ = Subtype

        class Different(CheckedPSet):
            __type__ = ChangedSubtype
        Different.__name__ = "Original"

        self.assert_catches_changes(Original, Different)

    def test_pvector_value_new_type(self):
        """
        If the type of the value of a ``PVector`` changes the output changes.
        """
        class Original(CheckedPVector):
            __type__ = int

        class Different(CheckedPVector):
            __type__ = str
        Different.__name__ = "Original"

        self.assert_catches_changes(Original, Different)

    def test_pvector_value_type_changed(self):
        """
        If the type of the value of a ``PVector`` is the same, but it has
        internally changed then the output changes.
        """
        class Original(CheckedPVector):
            __type__ = Subtype

        class Different(CheckedPVector):
            __type__ = ChangedSubtype
        Different.__name__ = "Original"

        self.assert_catches_changes(Original, Different)


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
        Most of the time if the configuration model changes this test will
        fail.

        This does not indicate a bug. Rather, it indicates that you should
        implement upgrade code for the on-disk configuration. Once you are
        confident it is possible to upgrade from older versions of Flocker
        to the new version of the code you have introduced, you can update
        this test by running:

            $ python -m flocker.control.test.test_model_change

        And then committing the resulting changes to git.

        Note that this test may *not* fail in some cases where you still
        need to write upgrade code, so don't rely on it to always tell you
        when you need to write upgrade code.
        """
        current_model = generate_model()
        previous_model = loads(PERSISTED_MODEL.getContent())[u"model"]
        self.assertEqual(current_model, previous_model,
                         self.test_model_changed.__doc__)


if __name__ == '__main__':
    persist_model()

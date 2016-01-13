# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Whenever the configuration model changes we need to write code to
upgrade the on-disk format from previous releases. This module will
automatically detect such changes by failing a test, ensuring that upgrade
code is always implemented when necessary.
"""

from json import loads, dumps

from pyrsistent import (
    PRecord, PClass, CheckedPSet, CheckedPVector, CheckedPMap, field,
)

from twisted.python.filepath import FilePath
from twisted.python.reflect import qual as fqpn

from .._persistence import ROOT_CLASS
from ... import __version__
from ...testtools import TestCase


PERSISTED_MODEL = FilePath(__file__).sibling(b"persisted_model.json")


def _precord_model(klass):
    """
    Serialize a ``PRecord`` or ``PClass`` model to something
    JSON-encodable.

    :param klass: A ``PRecord`` or ``PClass`` subclass.
    :return: Tuple of (model dictionary, further classes to process).
    """
    further_classes = set()
    if issubclass(klass, PRecord):
        attr_name = "_precord_fields"
    else:
        attr_name = "_pclass_fields"
    record = {u"category": u"record",
              u"fields": {}}
    for name, field_info in getattr(klass, attr_name).items():
        record[u"fields"][name] = sorted(
            fqpn(cls) for cls in field_info.type)
        for cls in field_info.type:
            further_classes.add(cls)
    return record, further_classes


def _pmap_model(klass):
    """
    Serialize a ``PMap`` model to something JSON-encodable.

    :param klass: A ``PMap`` subclass.
    :return: Tuple of (model dictionary, further classes to process).
    """
    record = {
        u"category": u"map",
        u"fields": {
            u"key": sorted(
                fqpn(cls) for cls in klass._checked_key_types),
            u"value": sorted(
                fqpn(cls) for cls in klass._checked_value_types)}}
    further_classes = set()
    for cls in klass._checked_key_types + klass._checked_value_types:
        further_classes.add(cls)
    return record, further_classes


def _psequence_model(klass):
    """
    Serialize a ``PVector`` or ``PSet`` model to something
    JSON-encodable.

    :param klass: A ``PVector`` or ``PSet`` subclass.
    :return: Tuple of (model dictionary, further classes to process).
    """
    category = u"set" if issubclass(klass, CheckedPSet) else u"list"
    record = {
        u"category": category,
        u"type": sorted(fqpn(cls) for cls in klass._checked_types),
    }
    further_classes = set(klass._checked_types)
    return record, further_classes


def _default_model(klass):
    """
    Default model for unhandled classes.

    :param klass: A class.
    :return: Tuple of (model dictionary, further classes to process).
    """
    return (None, set())


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
        if issubclass(klass, (PRecord, PClass)):
            to_model = _precord_model
        elif issubclass(klass, CheckedPMap):
            to_model = _pmap_model
        elif issubclass(klass, (CheckedPSet, CheckedPVector)):
            to_model = _psequence_model
        else:
            to_model = _default_model
        record, further_classes = to_model(klass)
        classes_result[klass_name] = record
        classes |= further_classes
    return result


class Subtype(PClass):
    """
    A sub-type used in ``GenerateModelTests``.
    """
OriginalSubtype = Subtype


class Subtype(PClass):
    """
    A changed variant of ``Subtype``.
    """
    x = field()
ChangedSubtype = Subtype
Subtype = OriginalSubtype


class GenerateModelTests(TestCase):
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
            # If not the calling test is buggy, since it's catching wrong
            # thing, a mere name change:
            (fqpn(original_class) == fqpn(changed_class),
             # Changes result in a difference:
             original_model != changed_model,
             # No changes result in same output:
             original_model == generate_model(original_class),
             changed_model == generate_model(changed_class)),
            (True, True, True, True))

    def test_different_class(self):
        """
        If a different root class is given the output changes.
        """
        class Original(PClass):
            pass

        class Different(PClass):
            pass

        self.assertNotEqual(generate_model(Original),
                            generate_model(Different))

    def test_precord_new_field(self):
        """
        If a new field is added to a ``PRecord`` the output changes.
        """
        class Different(PClass):
            pass
        Original = Different

        class Different(PClass):
            x = field()

        self.assert_catches_changes(Original, Different)

    def test_precord_removed_field(self):
        """
        If an existing field is removed from a ``PRecord`` the output
        changes.
        """
        class Different(PClass):
            x = field()
            y = field()
        Original = Different

        class Different(PClass):
            x = field()

        self.assert_catches_changes(Original, Different)

    def test_precord_field_changed_types(self):
        """
        If an existing field has its type changed in a ``PRecord`` the output
        changes.
        """
        class Different(PClass):
            x = field()
        Original = Different

        class Different(PClass):
            x = field(type=int)

        self.assert_catches_changes(Original, Different)

    def test_precord_field_type_changed(self):
        """
        If the an existing field in a ``PRecord`` has the same type, but the
        type changed somehow, the output changes.
        """
        class Different(PClass):
            x = field(type=Subtype)
        Original = Different

        class Different(PClass):
            x = field(type=ChangedSubtype)

        self.assert_catches_changes(Original, Different)

    def test_precord_field_types_reordered(self):
        """
        The order of types in a ``PRecord`` doesn't change the output.
        """
        class Different(PClass):
            x = field(type=(int, str))
        Original = Different

        class Different(PClass):
            x = field(type=(str, int))

        self.assertEqual(generate_model(Original),
                         generate_model(Different))

    def test_pclass_new_field(self):
        """
        If a new field is added to a ``PClass`` the output changes.
        """
        class Different(PClass):
            pass
        Original = Different

        class Different(PClass):
            x = field()

        self.assert_catches_changes(Original, Different)

    def test_pclass_removed_field(self):
        """
        If an existing field is removed from a ``PClass`` the output
        changes.
        """
        class Different(PClass):
            x = field()
            y = field()
        Original = Different

        class Different(PClass):
            x = field()

        self.assert_catches_changes(Original, Different)

    def test_pclass_field_changed_types(self):
        """
        If an existing field has its type changed in a ``PClass`` the output
        changes.
        """
        class Different(PClass):
            x = field()
        Original = Different

        class Different(PClass):
            x = field(type=int)

        self.assert_catches_changes(Original, Different)

    def test_pclass_field_type_changed(self):
        """
        If the an existing field in a ``PClass`` has the same type, but the
        type changed somehow, the output changes.
        """
        class Different(PClass):
            x = field(type=Subtype)
        Original = Different

        class Different(PClass):
            x = field(type=ChangedSubtype)

        self.assert_catches_changes(Original, Different)

    def test_pclass_field_types_reordered(self):
        """
        The order of types in a ``PClass`` doesn't change the output.
        """
        class Different(PClass):
            x = field(type=(int, str))
        Original = Different

        class Different(PClass):
            x = field(type=(str, int))

        self.assertEqual(generate_model(Original),
                         generate_model(Different))

    def test_pmap_key_new_type(self):
        """
        If the type of the key of a ``PMap`` changes the output changes.
        """
        class Different(CheckedPMap):
            __key_type__ = int
            __value_type__ = int
        Original = Different

        class Different(CheckedPMap):
            __key_type__ = str
            __value_type__ = int

        self.assert_catches_changes(Original, Different)

    def test_pmap_value_new_type(self):
        """
        If the type of the value of a ``PMap`` changes the output changes.
        """
        class Different(CheckedPMap):
            __key_type__ = int
            __value_type__ = int
        Original = Different

        class Different(CheckedPMap):
            __key_type__ = int
            __value_type__ = str

        self.assert_catches_changes(Original, Different)

    def test_pmap_key_type_changed(self):
        """
        If the type of the key of a ``PMap`` is the same, but it has
        internally changed then the output changes.
        """
        class Different(CheckedPMap):
            __key_type__ = Subtype
            __value_type__ = int
        Original = Different

        class Different(CheckedPMap):
            __key_type__ = ChangedSubtype
            __value_type__ = int

        self.assert_catches_changes(Original, Different)

    def test_pmap_value_type_changed(self):
        """
        If the type of the value of a ``PMap`` is the same, but it has
        internally changed then the output changes.
        """
        class Different(CheckedPMap):
            __key_type__ = int
            __value_type__ = Subtype
        Original = Different

        class Different(CheckedPMap):
            __key_type__ = int
            __value_type__ = ChangedSubtype

        self.assert_catches_changes(Original, Different)

    def test_pmap_key_types_reordered(self):
        """
        The order of types in a ``PMap`` key doesn't change the output.
        """
        class Different(CheckedPMap):
            __key_type__ = (int, str)
            __value_type__ = int
        Original = Different

        class Different(CheckedPMap):
            __key_type__ = (str, int)
            __value_type__ = int

        self.assertEqual(generate_model(Original),
                         generate_model(Different))

    def test_pmap_value_types_reordered(self):
        """
        The order of types in a ``PMap`` value doesn't change the output.
        """
        class Different(CheckedPMap):
            __value_type__ = (int, str)
            __key_type__ = int
        Original = Different

        class Different(CheckedPMap):
            __value_type__ = (str, int)
            __key_type__ = int

        self.assertEqual(generate_model(Original),
                         generate_model(Different))

    def test_pset_value_new_type(self):
        """
        If the type of the value of a ``PSet`` changes the output changes.
        """
        class Different(CheckedPSet):
            __type__ = int
        Original = Different

        class Different(CheckedPSet):
            __type__ = str

        self.assert_catches_changes(Original, Different)

    def test_pset_value_type_changed(self):
        """
        If the type of the value of a ``PSet`` is the same, but it has
        internally changed then the output changes.
        """
        class Different(CheckedPSet):
            __type__ = Subtype
        Original = Different

        class Different(CheckedPSet):
            __type__ = ChangedSubtype

        self.assert_catches_changes(Original, Different)

    def test_pset_value_types_reordered(self):
        """
        The order of types in a ``PSet`` type definition doesn't change the
        output.
        """
        class Different(CheckedPSet):
            __type__ = (int, str)
        Original = Different

        class Different(CheckedPSet):
            __type__ = (str, int)

        self.assertEqual(generate_model(Original),
                         generate_model(Different))

    def test_pvector_value_new_type(self):
        """
        If the type of the value of a ``PVector`` changes the output changes.
        """
        class Different(CheckedPVector):
            __type__ = int
        Original = Different

        class Different(CheckedPVector):
            __type__ = str

        self.assert_catches_changes(Original, Different)

    def test_pvector_value_type_changed(self):
        """
        If the type of the value of a ``PVector`` is the same, but it has
        internally changed then the output changes.
        """
        class Different(CheckedPVector):
            __type__ = Subtype
        Original = Different

        class Different(CheckedPVector):
            __type__ = ChangedSubtype

        self.assert_catches_changes(Original, Different)

    def test_pvector_value_types_reordered(self):
        """
        The order of types in a ``PVector`` type definition doesn't change the
        output.
        """
        class Different(CheckedPVector):
            __type__ = (int, str)
        Original = Different

        class Different(CheckedPVector):
            __type__ = (str, int)

        self.assertEqual(generate_model(Original),
                         generate_model(Different))


def persist_model():
    """
    Store the current model to disk.

    We also store the git hash of current checkout, so it's clear what
    version of code was used to generate the model.
    """
    model = generate_model()
    PERSISTED_MODEL.setContent(dumps(
        {u"version": __version__, u"model": model},
        sort_keys=True, indent=4, separators=(',', ': ')))


class ConfigurationModelChanged(TestCase):
    """
    Detect when the configuration model has changed.
    """
    def test_model_changed(self):
        """
        If the configuration model changes this test will (usually) fail.
        If you changed configuration and it didn't fail, see below.

        This failing test does not indicate a bug. Rather, it is a
        reminder that since you have changed the model, you MUST IMPLEMENT
        UPGRADE CODE for the on-disk configuration. Once you are confident
        it is possible to upgrade from older versions of Flocker to the
        new version of the code you have introduced, you can update this
        test by running:

            $ python -m flocker.control.test.test_model_change

        And then committing the resulting changes to git.

        Note that this test may *not* fail in some cases where you still
        need to write upgrade code, so don't rely on it to always tell you
        when you need to write upgrade code. In that case you should also
        try to extend this module so it catches that category of change
        next time someone makes it.
        """
        current_model = generate_model()
        previous_model = loads(PERSISTED_MODEL.getContent())[u"model"]
        self.assertDictEqual(current_model, previous_model,
                             self.test_model_changed.__doc__)


if __name__ == '__main__':
    persist_model()
    print("Persisted model for version {}.".format(__version__))

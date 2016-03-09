# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.common.plugin``
"""

from pyrsistent import PClass, field

from flocker.testtools import TestCase

from ..plugin import (
    PluginLoader,
    PluginNotFound,
    MissingPluginAttribute,
    InvalidPluginType,
)


class DummyDescription(PClass):
    """
    Dummy plugin type."
    """
    name = field(unicode, mandatory=True)


# The following test examples use classes instead of modules for
# namespacing. Real plugins should use modules.
class DummyPlugin(object):
    """
    A plugin."
    """
    FLOCKER_PLUGIN = DummyDescription(
        name=u"dummyplugin",
    )


class DummyPluginMissingAttribute(object):
    """
    A purported plugin that is missing the expected attribute.
    """


class DummyPluginWrongType(object):
    """
    A purported plugin that has the wrong type of description.
    """
    FLOCKER_PLUGIN = object()


DUMMY_LOADER = PluginLoader(
    builtin_plugins=[],
    module_attribute="FLOCKER_PLUGIN",
    plugin_type=DummyDescription,
)


class PluginLoaderTests(TestCase):
    """
    Tests for ``PluginLoader``.
    """

    def test_list_plugins(self):
        """
        ``PluginLoader.list`` returns the list of builtin plugins.
        """
        loader = DUMMY_LOADER.set(
            "builtin_plugins", [
                DummyDescription(name=u"other-builtin"),
                DummyDescription(name=u"builtin"),
            ]
        )
        plugins = loader.list()
        self.assertEqual(plugins, loader.builtin_plugins)

    def test_builtin_backend(self):
        """
        If the plugin name is that of a pre-configured plugin, the
        corresponding builtin plugin is returned.
        """
        loader = DUMMY_LOADER.set(
            "builtin_plugins", [
                DummyDescription(name=u"other-builtin"),
                DummyDescription(name=u"builtin"),
            ]
        )
        plugin = loader.get("builtin")
        self.assertEqual(plugin, DummyDescription(name=u"builtin"))

    def test_3rd_party_plugin(self):
        """
        If the plugin name is not that of a pre-configured plugin, the
        plugin name is treated as a Python import path, and the
        specified attribute of that is used as the plugin.
        """
        plugin = DUMMY_LOADER.get(
            "flocker.common.test.test_plugin.DummyPlugin"
        )
        self.assertEqual(plugin, DummyDescription(name=u"dummyplugin"))

    def test_wrong_package_3rd_party_backend(self):
        """
        If the plugin name refers to an unimportable package,
        ``PluginNotFound`` is raised.
        """
        self.assertRaises(
            PluginNotFound,
            DUMMY_LOADER.get,
            "notarealmoduleireallyhope",
        )

    def test_missing_attribute_3rd_party_backend(self):
        """
        If the plugin name refers to an object that doesn't have the
        specified attribute, ``MissingPluginAttribute`` is raised.
        """
        self.assertRaises(
            MissingPluginAttribute,
            DUMMY_LOADER.get,
            "flocker.common.test.test_plugin.DummyPluginMissingAttribute"
        )

    def test_wrong_attribute_type_3rd_party_backend(self):
        """
        If the plugin name refers to an object whose specified
        attribute isn't of the right type, ``InvalidPluginType`` is
        raised.
        """
        self.assertRaises(
            InvalidPluginType,
            DUMMY_LOADER.get,
            "flocker.common.test.test_plugin.DummyPluginWrongType"
        )

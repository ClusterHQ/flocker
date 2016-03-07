# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tools for loading third-party plugins.
"""

from characteristic import attributes
from pyrsistent import PClass, field, PVector, pvector
from twisted.python.reflect import namedAny


@attributes(["plugin_name"])
class PluginNotFound(Exception):
    """
    A plugin with the given name was not found.

    :attr str plugin_name: Name of the plugin looked for.
    """
    def __str__(self):
        return (
            "'{!s}' is neither a built-in plugin nor a 3rd party "
            "module.".format(self.plugin_name)
        )


class InvalidPlugin(Exception):
    """
    A module with the given plugin name was found, but doesn't
    provide a valid flocker plugin.
    """


@attributes(["plugin_name", "module_attribute"])
class MissingPluginAttribute(InvalidPlugin):
    """
    The named module doesn't have the attribute expected of plugins.
    """
    def __str__(self):
        return (
            "The 3rd party plugin '{plugin_name!s}' does not "
            "correspond to the expected interface. "
            "`{plugin_name!s}.{module_attribute!s}` is not defined."
            .format(
                plugin_name=self.plugin_name,
                module_attribute=self.module_attribute,
            )
        )


@attributes(["plugin_name", "plugin_type", "actual_type", "module_attribute"])
class InvalidPluginType(InvalidPlugin):
    """
    A plugin with the given name was not found.
    """
    def __str__(self):
        return (
            "The 3rd party plugin '{plugin_name!s}' does not "
            "correspond to the expected interface. "
            "`{plugin_name!s}.{module_attribute!s}` is of "
            "type `{actual_type.__name__}`, not `{plugin_type.__name__}`."
            .format(
                plugin_name=self.plugin_name,
                actual_type=self.actual_type,
                plugin_type=self.plugin_type,
                module_attribute=self.module_attribute,
            )
        )


class PluginLoader(PClass):
    """
    :ivar PVector builtin_plugins: The plugins shipped with flocker.
    :ivar str module_attribute: The module attribute that third-party plugins
        should declare.
    :ivar type plugin_type: The type describing a plugin.
    """
    builtin_plugins = field(PVector, mandatory=True, factory=pvector)
    module_attribute = field(str, mandatory=True)
    plugin_type = field(type, mandatory=True)

    def __invariant__(self):
        for builtin in self.builtin_plugins:
            if not isinstance(builtin, self.plugin_type):
                return (
                    False,
                    "Builtin plugins must be of `{plugin_type.__name__}`, not "
                    "`{actual_type.__name__}`.".format(
                        plugin_type=self.plugin_type,
                        actual_type=type(builtin),
                    )
                )

        return (True, "")

    def list(self):
        """
        Return a list of available plugins.

        .. note::

           This list may not include all third-party plugins.

        :return: The availble plugins.
        :rtype: ``PVector`` of ``plugin_type``s.
        """
        return self.builtin_plugins

    def get(self, plugin_name):
        """
        Find the plugin in ``builtin_plugins`` that matches the one named by
        ``plugin_name``. If not found then an attempt is made to load it as
        module describing a plugin.

        :param plugin_name: The name of the backend.
        :param backends: Collection of `BackendDescription`` instances.

        :raise PluginNotFound: If ``plugin_name`` doesn't match any
            known plugin.
        :raise InvalidPlugin: If ``plugin_name`` names a module that
            doesn't satisfy the plugin interface.
        :return: The matching ``plugin_type`` instance.
        """
        for builtin in self.builtin_plugins:
            if builtin.name == plugin_name:
                return builtin

        try:
            plugin_module = namedAny(plugin_name)
        except (AttributeError, ValueError):
            raise PluginNotFound(plugin_name=plugin_name)

        try:
            plugin = getattr(plugin_module, self.module_attribute)
        except AttributeError:
            raise MissingPluginAttribute(
                plugin_name=plugin_name,
                module_attribute=self.module_attribute,
            )

        if not isinstance(plugin, self.plugin_type):
            raise InvalidPluginType(
                plugin_name=plugin_name,
                plugin_type=self.plugin_type,
                actual_type=type(plugin),
                module_attribute=self.module_attribute,
            )

        return plugin

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


@attributes(["plugin_name", "plugin_type", "actual_type", "module_attribute"])
class InvalidPlugin(Exception):
    """
    A plugin with the given name was not found.

    :attr str plugin_name: Name of the plugin looked for.
    """
    def __str__(self):
        return (
            "The 3rd party plugin '{plugin_name!s}' does not "
            "correspond to the expected interface.\n"
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

    def get_plugin(self, plugin_name):
        """
        Find the backend in ``backends`` that matches the one named by
        ``backend_name``. If not found then attempt is made to load it as
        plugin.

        :param backend_name: The name of the backend.
        :param backends: Collection of `BackendDescription`` instances.

        :raise PluginNotFound: If ``backend_name`` doesn't match any
            known backend.
        :return: The matching ``BackendDescription``.
        """
        for builtin in self.builtin_plugins:
            if builtin.name == plugin_name:
                return builtin

        try:
            plugin = getattr(namedAny(plugin_name), self.module_attribute)
        except (AttributeError, ValueError):
            raise PluginNotFound(plugin_name=plugin_name)

        if not isinstance(plugin, self.plugin_type):
            raise InvalidPlugin(
                plugin_name=plugin_name,
                plugin_type=self.plugin_type,
                actual_type=type(plugin),
                module_attribute=self.module_attribute,
            )

        return plugin

from twisted.python.reflect import namedAny
from characteristic import attributes


@attributes(["plugin_name"])
class PluginNotFound(Exception):
    """
    A plugin with the given name was not found.

    :attr str plugin_name: Name of the plugin looked for.
    """


def get_plugin(plugin_name, builtins, module_attribute):
    """
    Find the backend in ``backends`` that matches the one named by
    ``backend_name``. If not found then attempt is made to load it as
    plugin.

    :param backend_name: The name of the backend.
    :param backends: Collection of `BackendDescription`` instances.

    :raise ValueError: If ``backend_name`` doesn't match any known backend.
    :return: The matching ``BackendDescription``.
    """
    for builtin in builtins:
        if builtin.name == plugin_name:
            return builtin
    try:
        return getattr(namedAny(plugin_name), module_attribute)
    except (AttributeError, ValueError):
        raise PluginNotFound(plugin_name=plugin_name)
        raise ValueError(
            "'{!s}' is neither a built-in backend nor a 3rd party "
            "module.".format(plugin_name),
        )

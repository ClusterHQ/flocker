# XXX move flocker.node._config here, and also add:


def marshal_to_application_config_format(deployment):
    """
    Convert ``Deployment`` into application configuration format.

    :param Deployment deployment: The current desired configuration.

    :return: Simple Python types suitable for serialization to YAML, in
        the application configuration format.
    """
    pass


def marshal_to_deployment_config_format(deployment):
    """
    Convert ``Deployment`` into deployment configuration format.

    :param Deployment deployment: The current desired configuration.

    :return: Simple Python types suitable for serialization to YAML, in
        the deployment configuration format.
    """
    pass

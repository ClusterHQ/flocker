from ._model import Volume, DockerImage, Node, Application, Deployment


def model_from_configuration(application_config, deployment_config):
    # {"version": 1,
    #  "applications": {
    #      "mysql-hybridcluster": {"image": "hybridlogic/mysql5.9:latest", "volume": "/var/run/mysql"}
    #  }
    # }
    assert application_config[u"version"] == 1
    applications = dict([
        (name, Application(
                    name,
                    DockerImage(*config[u"image"].rsplit(u":", 1)),
                    Volume(config[u"volume"])))
        for (name, config)
        in application_config[u"applications"].items()
        ])


    #
    # {"version": 1,
    #  "nodes": {
    #      "node1": ["mysql-hybridcluster"],
    #      "node2": ["site-hybridcluster.com"]
    #  }
    # }
    #
    assert deployment_config[u"version"] == 1

    nodes = {
        Node(hostname, [applications[app_name] for app_name in app_names])
        for (hostname, app_names)
        in deployment_config[u"nodes"].items()
        }

    return Deployment(nodes)

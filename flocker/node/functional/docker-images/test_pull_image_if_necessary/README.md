This is a do-nothing image that exists for use by the Flocker test suite.
It exists only to verify that an image not locally present is pulled automatically.
It is never used to start a container so it will always be possible to remove it and necessitate a pull.
This image is configured as an "Automated Build" on Docker Hub.
See flocker.node.functional.test_docker.NamespacedDockerClientTests.test_pull_image_if_necessary for further usage details.

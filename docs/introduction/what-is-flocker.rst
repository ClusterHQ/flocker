================
What is Flocker?
================

Flocker is an open-source Container Data Volume Manager for your Dockerized applications.

By providing tools for data migrations, Flocker gives ops teams the tools they need to run containerized stateful services like databases in production.

Unlike a Docker data volume which is tied to a single server, a Flocker data volume, called a dataset, is portable and can be used with any container, no matter where that container is running.

Flocker manages Docker containers and data volumes together.
When you use Flocker to manage your stateful microservice, your volumes will follow your containers when they move between different hosts in your cluster.

You can also use Flocker to manage only your volumes, while continuing to manage your containers however you choose.
To use Flocker to manage your volumes while tools like Docker, Docker Swarm or Mesos manage your containers, you can use :ref:`docker-plugin`.

.. image:: images/flocker-v-native-containers.svg
   :alt: Migrating data: Native Docker versus Flocker.
         In native Docker, when a container moves, its data volume stays in place.
		 Database starts on a new server without any data.
		 When using Flocker, when a container moves, the data volume moves with it.
		 Your database gets to keep its data!

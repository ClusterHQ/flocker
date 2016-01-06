===================================================
Tutorial: using Flocker with Docker, Swarm, Compose
===================================================

This tutorial will guide you through deploying a sample application, consisting of two containers (one stateless application container and one stateful database container), on a Swarm cluster using Flocker as a volume driver.

It will then demonstrate moving both containers from one node to another.

Because we do not have a networking solution in this example, we will use Swarm constraints to force both containers to be on the same node each time we deploy them.

Prerequisites
=============

* A Flocker cluster with Swarm installed (:ref:`get one here <docker-integration>`)
* A client machine with Docker Compose installed and access to the Swarm master (if you used our CloudFormation installer, SSH into the "client" VM provided)


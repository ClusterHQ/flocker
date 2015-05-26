=======================
Introduction to Flocker
=======================

Motivation for Building Flocker
===============================
Flocker lets you move your Docker containers and their data together between Linux hosts.
This means that you can run your databases, queues and key-value stores in Docker and move them around as easily as the rest of your app.
Even stateless apps depend on many stateful services and currently running these services in Docker containers in production is nearly impossible.
Flocker aims to solve this problem by providing an orchestration framework that allows you to port both your stateful and stateless containers between environments.

Docker allows for multiple isolated, reproducible application environments on a single node: "containers".
Application state can be stored on a local disk in "volumes" attached to containers.
And containers can talk to each other and the external world via specified ports.

But what happens if you have more than one node?
How does application state work if you move containers around?
Flocker solves this problem by moving your volumes to where your applications are.

The diagram below provides a high level representation of how Flocker addresses these questions.

.. image:: images/flocker-architecture-diagram.jpg
   :alt: Containers run on physical nodes with Local Storage (ZFS).
         Flocker's proxying layer allows you to communicate with containers by routing traffic to any node.
         Filesystem state gets moved around with ZFS.

Future versions of Flocker will also support network block storage like EBS and OpenStack Cinder.

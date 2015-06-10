.. _routing:

===========================
Setting up External Routing
===========================

Flocker allows you to expose public ports on your applications.
For example, you can export port 8443 on an HTTPS server running inside a container as an externally visible port 443 on the host machine.
Because Flocker runs on a cluster of nodes your web application might run on different nodes at different times.
You could update the DNS record every time a container moves.
However, updating DNS records can take anywhere from a minute to a few hours to take effect for all clients so this will impact your application's availability.
This is where Flocker's routing functionality comes in handy.

When an external route is configured (e.g. on port 443) Flocker routes that port on *all* nodes to the node where your application is running.
You can therefore move a node and then change your DNS configuration appropriately without incurring any downtime.


No-Change DNS Configuration
===========================

What's more it is also possible to configure your DNS records in such a way that no DNS changes are necessary when applications move to different nodes.
Specifically, the DNS record for your application should be configured to point at all IPs in the cluster.

For example, consider the following setup:

.. image:: routing.svg
   :align: center
   :alt: Example of external port routing

``www.example.com`` has a DNS record pointing at two different nodes' IP.
Every time you connect to ``www.example.com`` your browser will choose one of the two IPs at random.

* If you connect to port 80 on the ``node2`` — which is not hosting the container — the traffic will be routed on to ``node1``.
* If you connect to port 80 on ``node1`` you will reach the web server that is listening on port 8080 within a container.

Note that if nodes are in different data centers and you pay for bandwidth this configuration will require you to pay for forwarded traffic between nodes.

.. _benchmarking:

Benchmarking
============

.. note::

   For the ``benchmark`` command described on this page, if the cluster uses private addresses for communication (e.g. AWS nodes), set the environment variable ``FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS`` to a serialized JSON object mapping cluster internal IP addresses to public IP addresses.
   This environment variable is provided if the cluster is started using the ``run-acceptance-tests`` command.
   This is intended to be a temporary requirement, until other mechanisms are available [:issue:`2137`, :issue:`3514`, :issue:`3521`].

Flocker includes a tool for benchmarking operations.
It is called like this:

.. prompt:: bash $

   benchmark/benchmark <options>


The :program:`benchmark` script has several options:

.. program:: benchmark

.. option:: --control <control-service-ipaddr>

   Specifies the IP address for the Flocker cluster control node.
   This must be specified, unless the ``no-op`` operation is requested.

.. option:: --certs <directory>

   Specifies the directory containing the user certificates.
   Defaults to the directory ``./certs``.

.. option:: --scenario <scenario>

   Specifies the scenario to run the benchmark under.
   Supported values include:

      ``no-load``
         No additional load on system.
         This is the default.

.. option:: --operation <operation>

   Specifies the operation to be benchmarked.
   This operation is sampled 3 times.
   Supported values include:

      ``no-op``
         A no-op operation that performs no action.

      ``read-request``
         Read from the control service.
         This is the default.

      ``wait-10``
         Wait 10 seconds between measurements.

.. option:: --metric <metric>

   Specifies the quantity to measure while the operation is performed.
   Supported values include:

      ``cputime``
         CPU time elapsed.

      ``wallclock``
         Actual clock time elapsed.
         This is the default.

To see the supported values for each option, run:

.. prompt:: bash $

   benchmark/benchmark --help

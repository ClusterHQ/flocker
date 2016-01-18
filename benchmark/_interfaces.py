# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Interfaces for the control service benchmarks.
"""

from zope.interface import Interface


class IScenario(Interface):
    """
    A scenario in which an operation occurs.
    """

    def start():
        """
        :return: A Deferred that fires when the desired scenario is
            established (e.g. that a certain load is being applied).
        """

    def maintained():
        """
        A test scenario may be difficult to maintain. For example, it may
        require maintaining a load against a remote resource.  If the scenario
        cannot be maintained, then the benchmarks may be invalid.  This
        function returns a Deferred which fires with an errBack if the scenario
        cannot be maintained.

        :return: A Deferred that fires with an errback if the desired
            scenario fails to hold between being established and being
            stopped.  This Deferred never fires with a callback.
        """

    def stop():
        """
        Stop the scenario from being maintained.

        :return Deferred[Optional[Dict[unicode, Any]]]: Scenario metrics.
        """


class IProbe(Interface):
    """
    A probe that performs an operation.
    """

    def run():
        """
        Run the operation.  This should run with as little overhead as
        possible, in order to ensure benchmark measurements are accurate.

        :return: A Deferred firing with the result of the operation.
        """

    def cleanup():
        """
        Perform any cleanup required after the operation.  This is performed
        outside the benchmark measurement.

        :return: A Deferred firing when the cleanup is finished.
        """


class IOperation(Interface):
    """
    An operation that can be performed.
    """

    def get_probe():
        """
        Get a probe for the operation. To ensure sequential operations perform
        real work, the operation may return a different probe each time.
        """


class IMetric(Interface):
    """
    A metric to be measured.
    """

    def measure(f, *a, **kw):
        """
        Measure the change in the metric while performing a function.

        :param f: The measured function, which must return a Deferred.
        :param a: Positional arguments to function ``f``.
        :param kw: Keyword arguments to function ``f``.
        :return: Deferred firing when measurement has been taken, with the
            value of the measurement.
        """


class IRequestScenarioSetup(Interface):
    """
    Setup for a load scenario.
    It will provide a setup function and a make request function to
    make requests of a certain type
    """
    def run_setup():
        """
        Interface for the scenario load setup. It should do all the actions
        needed to configure the environment to make the requests defined in
        the ``make_request`` function, like creating dataset or configuring
        all we need in the cluster.

        :return: ``Deferred`` firing once the setup has been completed and the
            requests defined in ``make_request`` can be safely done. It should
            have a timeout set so the Deferred fails if something went wrong
            and the setup got stuck.
        """
    def make_request():
        """
        Interface for request generator
        This function will make a single REST request. It can use everything
        that has been setup and/or created in ``run_setup``, and has the
        pre-requesite that ``run_setup`` has successfully finished.

        :return: ``Deferred`` that fires when the REST request has been
            completed, and returns the results of the request.
        """

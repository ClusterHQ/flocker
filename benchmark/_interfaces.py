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


class IRequest(Interface):
    """
    A request that may require setup and cleanup.
    """

    def run_setup():
        """
        Perform any steps that need to be done before a request.

        :return Deferred: firing once the setup has been completed and the
            requests defined in ``make_request`` can be safely done.
        """

    def make_request():
        """
        This function will make a single request. It can use everything
        that has been setup and/or created in ``run_setup``, and has the
        pre-requisite that ``run_setup`` has successfully finished.

        :return Deferred: that fires when the REST request has been
            completed, and returns the results of the request.
        """

    def run_cleanup():
        """
        Interface function for the request cleanup, to delete anything that
        might have been created or modified.

        :return Deferred: that will fire once the cleanup is completed.
        """

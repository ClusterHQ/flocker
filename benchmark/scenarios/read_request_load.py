# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Read request load scenario for the control service benchmarks.
"""

from zope.interface import implementer

from twisted.internet.defer import succeed

from flocker.apiclient import IFlockerAPIV1Client

from .._interfaces import IRequestScenarioSetup
from .._method import validate_no_arg_method
from ._request_load import RequestLoadScenario, DEFAULT_SAMPLE_SIZE


@implementer(IRequestScenarioSetup)
class ReadRequest(object):
    """
    Implementation of the setup and request maker for the read load
    scenario.

    :ivar Callable[[], Deferred[Any]] request: Callable to perform the
        read request.
    """
    def __init__(self, request):
        self._request = request

    def make_request(self):
        """
        Function that will make a single read request.
        It will list the nodes on the cluster given when initialising
        the ``ReadRequest`` class

        :return: A ``Deferred`` that fires when the request has been performed.
        """
        return self._request()

    def run_setup(self):
        """
        No setup is required for the read scenario, so this is a no-op
        setup.

        :return: A ``Deferred`` that fires instantly with a success result.
        """
        return succeed(None)


def read_request_load_scenario(
    reactor, cluster, method='version', request_rate=10,
    sample_size=DEFAULT_SAMPLE_SIZE, timeout=45, tolerance_percentage=0.2
):
    """
    Factory that will initialise and return an excenario that places
    load on the cluster by performing read requests at a specified rate.

    :param reactor: Reactor to use.
    :param cluster: ``BenchmarkCluster`` containing the control service.
    :param method: Method of ``IFlockerAPIV1Client`` to call.
    :param request_rate: The target number of requests per second.
    :param sample_size: The number of samples to collect when measuring
        the rate.
    :param timeout: Maximum time in seconds to wait for the requested
        rate to be reached.
    :param tolerance_percentage: error percentage in the rate that is
        considered valid. For example, if we request a ``request_rate``
        of 20, and we give a tolerance_percentage of 0.2 (20%), anything
        in [16,20] will be a valid rate.

    :return: a ``RequestLoadScenario`` initialised to be a read load
        scenario.
    """
    validate_no_arg_method(IFlockerAPIV1Client, method)
    request = getattr(cluster.get_control_service(reactor), method)
    return RequestLoadScenario(
        reactor,
        ReadRequest(request),
        request_rate=request_rate,
        sample_size=sample_size,
        timeout=timeout,
        tolerance_percentage=tolerance_percentage,
    )

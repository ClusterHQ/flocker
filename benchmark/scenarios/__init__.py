# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Shared benchmarking scenarios components.

:var int DEFAULT_SAMPLE_SIZE: default size of the benchmarking
    sample size.
"""

__all__ = [
    'read_request_load_scenario', 'write_request_load_scenario',
    'DatasetCreationTimeout', 'RateMeasurer',
    'RequestRateTooLow', 'RequestRateNotReached',
    'RequestOverload', 'NoNodesFound', 'RequestLoadScenario',

    'DEFAULT_SAMPLE_SIZE',
]

from .no_load import NoLoadScenario
from .read_request_load import read_request_load_scenario

from .write_request_load import (
    write_request_load_scenario, DatasetCreationTimeout
)
from ._rate_measurer import RateMeasurer, DEFAULT_SAMPLE_SIZE
from ._request_load import (
    RequestRateTooLow, RequestRateNotReached,
    RequestOverload, NoNodesFound, RequestLoadScenario,
    RequestScenarioAlreadyStarted
)

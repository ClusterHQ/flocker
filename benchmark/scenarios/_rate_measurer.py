# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
from collections import deque

DEFAULT_SAMPLE_SIZE = 5


class RateMeasurer(object):
    """
    Measures the rate of requests in requests per second.

    :ivar sample_size: The number of samples to collect.
    :ivar _samples: The recorded samples.
    :ivar _sent: The number of sent requests recorded.
    :ivar _received: The number of received requests recorded.
    :ivar _error_count: The number of failed requests recorded.
    :ivar _rate: The current rate.
    :ivar Mapping[int, int] _call_durations: The number of times a call took
        the given time (rounded to 1 decimal place).
    :ivar Mapping[str, int] _errors: The number of times the given error
        message was received.
    """

    def __init__(self, sample_size=DEFAULT_SAMPLE_SIZE):
        self.sample_size = sample_size
        self._samples = deque([0] * sample_size, sample_size)
        self._sent = 0
        self._received = 0
        self._error_count = 0
        self._rate = 0
        self._call_durations = {}
        self._errors = {}

    def request_sent(self):
        """
        Increase the number of sent requests.
        """
        self._sent += 1

    def response_received(self, duration):
        """
        Increase the number of received requests.

        :param float duration: Time taken to perform call
        """
        self._received += 1
        key = round(duration, 1)
        self._call_durations[key] = self._call_durations.get(key, 0) + 1

    def request_failed(self, failure):
        """
        Increase the error count for failed requests.

        :param Failure failure: Failure
        """
        self._error_count += 1
        key = failure.getErrorMessage()
        self._errors[key] = self._errors.get(key, 0) + 1

    def update_rate(self):
        """
        Update the current rate and record a new sample.
        """
        self._rate = (
            (self._received - self._samples[0]) / float(self.sample_size)
        )
        self._samples.append(self._received)

    def outstanding(self):
        """
        Return the number of outstanding requests.
        """
        return self._sent - self._received - self._error_count

    def rate(self):
        """
        Return the current rate.
        """
        return self._rate

    def get_metrics(self):
        """
        Return the collected metrics.
        """
        return {
            'call_durations': self._call_durations,
            'errors': self._errors,
            'ok_count': self._received,
            'err_count': self._error_count,
        }

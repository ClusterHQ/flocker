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
    :ivar _errors: The number of failed requests recorded.
    :ivar _rate: The current rate.
    """

    def __init__(self, sample_size=DEFAULT_SAMPLE_SIZE):
        self.sample_size = sample_size
        self._samples = deque([0] * sample_size, sample_size)
        self._sent = 0
        self._received = 0
        self._errors = 0
        self._rate = 0

    def request_sent(self):
        """
        Increase the number of sent requests.
        """
        self._sent += 1

    def response_received(self, ignored):
        """
        Increase the number of received requests.

        :param ignored: The result of a callback. This parameter is
            not used.
        """
        self._received += 1

    def request_failed(self, ignored):
        """
        Increase the error count for failed requests.

        :param ignored: The result of a callback. This parameter is
            not used.
        """
        self._errors += 1

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
        return self._sent - self._received - self._errors

    def rate(self):
        """
        Return the current rate.
        """
        return self._rate

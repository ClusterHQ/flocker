# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node.agents.cinder`` against a fake, mimic-based cinder
API.
"""

# Maybe start a mimic server and use it to test authentication
# step...although not sure it's worth doing that since we'll already be testing
# against rackspace.
# * https://github.com/rackerlabs/mimic
# Ideally, this unit test module would run all the make_iblockdeviceapi_tests
# against authenticated_cinder_api which interacting only with mimic, but
# Mimic doesn't currently fake the cinder APIs
# (perhaps we could contribute that feature...or perhaps we haven't got time)
# See https://github.com/rackerlabs/mimic/issues/218

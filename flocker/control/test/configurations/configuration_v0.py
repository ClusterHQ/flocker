# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

# Generate a v0 configuration.

from json import dumps

if __name__ == "__main__":
    print dumps({u"$__class__$": u"Deployment"})

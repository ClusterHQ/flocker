# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for hybridcluster/publicapi/schemas.
"""

from twisted.trial.unittest import SynchronousTestCase
from jsonschema.exceptions import ValidationError

from flocker.restapi._schema import getValidator
from flocker.volume.httpapi import SCHEMAS

def withoutItem(mapping, key):
    """
    Return a shallow copy of C{mapping} without C{key}.

    @param mapping: A copyable mapping.
    @param key: The key to exclude from the copy.
    """
    without = mapping.copy()
    del without[key]
    return without



def withItems(mapping, newValues):
    """
    Return a shallow copy of C{mapping} with new values replacing old ones.

    @param mapping: A copyable mapping.
    @param newValues: A mapping to overwrite existing values.
    """
    withAdded = mapping.copy()
    withAdded.update(newValues)
    return withAdded



def buildSchemaTest(name, schema, failingInstances, passingInstances):
    """
    Create test case verifying that various instances pass and fail
    verification with a given JSON Schema.

    @param name: Name of test case to create
    @type name: L{str}

    @param schema: Schema to test
    @type schema: L{dict}
    @param failingInstances: List of instances which should fail validation
    @param passingInstances: List of instances which should pass validation

    @return The test case.
    @rtype: A L{SynchronousTestCase} subclass.
    """
    body = {
        'schema': schema,
        'validator': getValidator(schema, SCHEMAS),
        'passingInstances': passingInstances,
        'failingInstances': failingInstances,
        }
    for i, inst in enumerate(failingInstances):
        def test(self, inst=inst):
            self.assertRaises(ValidationError,
                    self.validator.validate, inst)
        test.__name__ = 'test_failsValidation_%d' % (i,)
        body[test.__name__] = test

    for i, inst in enumerate(passingInstances):
        def test(self, inst=inst):
            self.validator.validate(inst)
        test.__name__ = 'test_passesValidation_%d' % (i,)
        body[test.__name__] = test

    return type(name, (SynchronousTestCase, object), body)


_FAILING_NODENAMES = [
    # Not a string.
    10, {}, [], False,

    # Strings that are not IPv4 addresses.
    "hello", "1.2.3.4.5", "256.1.2.3", "-1.2.3.4", "1.2.3.4.", ".1.2.3.4",

    # Strings that are not dotted-quad formatted IPv4 addresses.
    # These are erroneously accepted.
    # https://www.pivotaltracker.com/story/show/66089428
    # "127.1", "0x7f000001", "017700000001", "2130706433",
    ]

_PASSING_NODENAMES = [
    "1.2.3.4", "255.255.255.255", "1.0.0.1",
    ]

NodenameTests = buildSchemaTest(
    name="NodenameTests",
    schema={'$ref': '/v2/types.json#/definitions/nodename'},
    failingInstances=_FAILING_NODENAMES,
    passingInstances=_PASSING_NODENAMES,
)



VersionTests = buildSchemaTest(
    name="VersionTests",
    schema={'$ref': '/v2/types.json#/definitions/version'},
    failingInstances=[
        # Missing version information
        {},
        # Unexepected information
        {'revision': 'abcd', 'branch': 'asdf', 'unexepected': 5},
        # Wrong type for 'branch'
        {'revision': 'abcd', 'branch': 5},
        # Wrong type for 'revision'
        {'revision': 5, 'branch': 'asdf'},
        # 'revision' is requried
        {'branch': 'asdf'},
        # 'branch' is requried
        {'revision': 'asdf'},
    ],
    passingInstances=[
        {'revision': 'asdf', 'branch': 'asdf'},
    ],
)



VersionsTests = buildSchemaTest(
    name="VersionsTests",
    schema={'$ref': '/v2/endpoints.json#/definitions/versions'},
    failingInstances=[
        # Missing version information
        {},
        # Wrong type for SiteJuggler version
        {'SiteJuggler': []},
        # Missing 'SiteJuggler' version
        {'OtherService': {'revision':'asf', 'branch': 'asdf'}},
        # Unexpected service version has wrong type
        {
            'SiteJuggler': {'revision': 'asdf', 'branch': 'asdf'},
            'OtherService': 'not a version',
        },
    ],
    passingInstances=[
        {'SiteJuggler': {'revision': 'asdf', 'branch': 'asdf'}},
        # Unexpected services are accepted.
        {
            'SiteJuggler': {'revision': 'asdf', 'branch': 'asdf'},
            'OtherService': {'revision': 'asdf', 'branch': 'asdf'}
        },
    ],
)



VarnishConfigurationTests = buildSchemaTest(
    name="VarnishConfigurationTests",
    schema={"$ref": '/v2/endpoints.json#/definitions/varnish_configuration'},
    failingInstances=[
        # Not objects:
        1, "", None, [], False,
        # Missing keys:
        {"enabled": True}, {"customer_vcl", "x"}, {},
        # Wrong types:
        {"enabled": True, "customer_vcl": 1},
        {"enabled": True, "customer_vcl": None},
        {"enabled": True, "customer_vcl": []},
        {"enabled": True, "customer_vcl": {}},
        {"enabled": True, "customer_vcl": False},
        {"enabled": None, "customer_vcl": ""},
        {"enabled": 1, "customer_vcl": ""},
        {"enabled": [], "customer_vcl": ""},
        {"enabled": {}, "customer_vcl": ""},
        {"enabled": "", "customer_vcl": ""},
    ],
    passingInstances=[
        {"enabled": True, "customer_vcl": ""},
        {"enabled": False, "customer_vcl": "xxx"},
    ],
)



_FAILING_IDS = [None, False, 10, ["hello"], {}]
_PASSING_IDS = ["abcdefg"]

WebsiteIDTests = buildSchemaTest(
    name='WebsiteIDTests',
    schema={'$ref': '/v2/types.json#/definitions/website_id'},
    failingInstances=_FAILING_IDS,
    passingInstances=_PASSING_IDS,
)



UserIDTests = buildSchemaTest(
    name='UserIDTests',
    schema={'$ref': '/v2/types.json#/definitions/user_id'},
    failingInstances=_FAILING_IDS,
    passingInstances=_PASSING_IDS,
)



MailboxIDTests = buildSchemaTest(
    name='MailboxIDTests',
    schema={'$ref': '/v2/types.json#/definitions/mailbox_id'},
    failingInstances=_FAILING_IDS,
    passingInstances=_PASSING_IDS,
)



DomainIDTests = buildSchemaTest(
    name='DomainIDTests',
    schema={'$ref': '/v2/types.json#/definitions/domain_id'},
    failingInstances=_FAILING_IDS,
    passingInstances=_PASSING_IDS,
)



DatabaseIDTests = buildSchemaTest(
    name='DatabaseIDTests',
    schema={'$ref': '/v2/types.json#/definitions/database_id'},
    failingInstances=_FAILING_IDS,
    passingInstances=_PASSING_IDS,
)



CertificateIDTests = buildSchemaTest(
    name='CertificateIDTests',
    schema={'$ref': '/v2/types.json#/definitions/certificate_id'},
    failingInstances=_FAILING_IDS,
    passingInstances=_PASSING_IDS,
)


_FAILING_TLS = [None, False, 10, ["hello"], {}]
_PASSING_TLS = ["abcdefg"]

TLSKeyTests = buildSchemaTest(
    name="TLSKeyTests",
    schema={'$ref': '/v2/types.json#/definitions/tls_key'},
    failingInstances=_FAILING_TLS,
    passingInstances=_PASSING_TLS,
)



TLSCertificateTests = buildSchemaTest(
    name="TLSCertificateTests",
    schema={'$ref': '/v2/types.json#/definitions/tls_certificate'},
    failingInstances=_FAILING_TLS,
    passingInstances=_PASSING_TLS,
)



TLSCertificateChainTests = buildSchemaTest(
    name="TLSCertificateChainTests",
    schema={'$ref': '/v2/types.json#/definitions/tls_certificate_chain'},
    failingInstances=_FAILING_TLS,
    passingInstances=_PASSING_TLS,
)



_PASSING_PASSWORD = {'password': 'abcdef'}

CredentialTests = buildSchemaTest(
    name='CredentialTests',
    schema={'$ref': '/v2/types.json#/definitions/credential'},
    failingInstances=[
        # No credentials
        {},
        # Unknown credential type
        {'unknown-credential': 'stuff'},
        # Credentials with additional fields
        {'password': 'abc', 'other': 'abc'},
        {'ssh_public_key': 'abc', 'other': 'abc'},
        # Multiple credentials types
        {'password': 'abc', 'ssh_public_key': 'abc'},
        # Wrong type in credential
        {'password': 5},
        {'ssh_public_key': 5},
    ],
    passingInstances=[
        _PASSING_PASSWORD,
        {'ssh_public_key': 'id-rsa stuff'},
    ],
)



CredentialsTests = buildSchemaTest(
    name='CredentialsTests',
    schema={'$ref': '/v2/types.json#/definitions/credentials'},
    failingInstances=[
        # Not arrays.
        None, False, 10, {},

        # Arrays containing objects that are not valid credentials.
        [None], [False], [{}], [{'password': 'abcdef'}, 3],
    ],
    passingInstances=[
        [{'password': 'abcdef'}],
    ],
)



GenericRouteTests = buildSchemaTest(
    name='GenericRouteTests',
    schema={'$ref': '/v2/types.json#/definitions/route'},
    failingInstances=[
        # No realm
        {},
        # Unknown realm.
        {'realm': 'not-recognized'},
    ],
    passingInstances=[],
)


# /definitions/route can support different types of routes, so we test each
# one in isolation.

_PASSING_HOSTNAME = {'realm': 'hostname', 'hostname': 'abc.com'}

HostnameRouteTests = buildSchemaTest(
    name='HostnameRouteTests',
    schema={'$ref': '/v2/types.json#/definitions/route'},
    failingInstances=[
        {'hostname': 'abc'},
        {'realm': 'hostname'},
        # Realm missing additional keys
        {'realm': 'hostname', 'other': 5},
        {'realm': 'hostname', 'hostname': 'abc', 'other': 5},
    ],
    passingInstances=[
        _PASSING_HOSTNAME,
    ],
)



_PASSING_EMAIL_ADDRESS = {'realm': 'email_address',
                          'local_name': 'alice',
                          'domain_id': '123'}

EmailRouteTests = buildSchemaTest(
    name='EmailRouteTests',
    schema={'$ref': '/v2/types.json#/definitions/route'},
    failingInstances=[
        {'local_name': 'abc', 'domain_id': '123'},
        {'realm': 'email_address'},
        {'realm': 'email_address', 'other': 5},
        {'realm': 'email_address', 'local_name': 'abc', 'other': 5},
        {'realm': 'email_address', 'domain_id': '123', 'other': 5},
        {'realm': 'email_address', 'domain_id': '1', 'local_name': 'ab', 'other': 5},
        {'realm': 'email_address', 'domain_id': '1', 'local_name': ''},
        {'realm': 'email_address', 'domain_id': '1', 'local_name': '!'},
        {'realm': 'email_address', 'domain_id': '1', 'local_name': '.'},
        {'realm': 'email_address', 'domain_id': '1', 'local_name': '-'},
        {'realm': 'email_address', 'domain_id': '1', 'local_name': 'a@b.c'},
        {'realm': 'email_address', 'domain_id': '1', 'local_name': u'\N{SNOWMAN}'},
    ],
    passingInstances=[
        _PASSING_EMAIL_ADDRESS,
        {'realm': 'email_address', 'local_name': 'alice.al', 'domain_id': '123'},
        {'realm': 'email_address', 'local_name': 'alice-al', 'domain_id': '123'},
        {'realm': 'email_address', 'local_name': '123', 'domain_id': '123'},
        {'realm': 'email_address', 'local_name': '1', 'domain_id': '123'},
        {'realm': 'email_address', 'local_name': 'z', 'domain_id': '123'},
    ],
)



_PASSING_DATABASE_ADDRESS = {'realm': 'mysql',
                             'database_name': 'examplecom'}

DatabaseRouteTests = buildSchemaTest(
    name='DatabaseRouteTests',
    schema={'$ref': '/v2/types.json#/definitions/route'},
    failingInstances=[
        # Missing values:
        {'database_name': '123'},
        {'realm': 'mysql'},
        {'realm': 'mysql', 'other': 5},
        # Extra values:
        {'realm': 'mysql', 'database_name': 'abc', 'other': 5},
        # Bad values:
        {'realm': 'mysql', 'database_name': '!'},
        {'realm': 'mysql', 'database_name': 2},
        # Too long
        {'realm': 'mysql', 'database_name': '01234567890123456'},
    ],
    passingInstances=[
        _PASSING_DATABASE_ADDRESS,
        {'realm': 'mysql', 'database_name': 'a_b'},
        {'realm': 'mysql', 'database_name': 'AZ'},
        {'realm': 'mysql', 'database_name': '0123456789abcdef'},
    ],
)



def buildRoutesTest(name, schema, supportedRoutes, unsupportedRoutes,
                    minLength, maxLength):
    """
    Build tests for a specific routes definition.

    @param name: Name of test case to create
    @type name: L{str}

    @param schema: Schema to test
    @type schema: L{dict}

    @param supportedRoutes: Route instances that can be put in the routes
        array. E.g. I{email_address} route if this is for mailboxes.
    @type supportedRoutes: L{list} of L{dict}

    @param unsupportedRoutes: Route instances that are otherwise valid but
        can't be put in the routes array. E.g. I{hostname} route if this for
        websites.
    @type unsupportedRoutes: L{list} of L{dict}

    @param minLength: Minimum number of required routes.
    @type minLength: L{int}

    @param maxLength: Maximum number of allowed routes.
    @type maxLength: L{int}

    @return The test case.
    @rtype: A L{SynchronousTestCase} subclass.
    """
    failingInstances=([
        # Not arrays.
        None, False, 10, {},

        # Arrays containing objects that are not valid routes.
        [None], [False], [{}], [supportedRoutes[0], 3]] +

        # Valid routes not supported in this case:
        [[unsupported] for unsupported in unsupportedRoutes])
    passingInstances=[supportedRoutes]

    if minLength == 0:
        passingInstances.append([])
    else:
        failingInstances.append([])
    failingInstances.append([supportedRoutes[0]] * (maxLength + 1))

    return buildSchemaTest(
        name=name,
        schema=schema,
        failingInstances=failingInstances,
        passingInstances=passingInstances
        )



WebsiteRoutesTests = buildRoutesTest(
    name='WebsiteRoutesTests',
    schema={'$ref': '/v2/types.json#/definitions/website_routes'},
    supportedRoutes=[_PASSING_HOSTNAME],
    unsupportedRoutes=[_PASSING_EMAIL_ADDRESS, _PASSING_DATABASE_ADDRESS],
    minLength=1, maxLength=1,
)



MailboxRoutesTests = buildRoutesTest(
    name='MailboxRoutesTests',
    schema={'$ref': '/v2/types.json#/definitions/mailbox_routes'},
    supportedRoutes=[_PASSING_EMAIL_ADDRESS],
    unsupportedRoutes=[_PASSING_HOSTNAME, _PASSING_DATABASE_ADDRESS],
    minLength=1, maxLength=1,
)



DatabaseRoutesTests = buildRoutesTest(
    name='DatabaseRoutesTests',
    schema={'$ref': '/v2/types.json#/definitions/database_routes'},
    supportedRoutes=[_PASSING_DATABASE_ADDRESS],
    unsupportedRoutes=[_PASSING_HOSTNAME, _PASSING_EMAIL_ADDRESS],
    minLength=1, maxLength=1,
)



_PASSING_TEMPLATE = {"name": "foobar"}

TemplateTests = buildSchemaTest(
    name='TemplateTests',
    schema={'$ref': '/v2/types.json#/definitions/template'},
    failingInstances=[
        # Not objects.
        None, False, 10, [{}],

        # Missing a name property.
        {"foo": "bar"},

        # Extra properties beyond the name property.
        {"foo": "bar", "name": "baz"},

        # Non-string name value.
        {"name": 10},
    ],
    passingInstances=[
        _PASSING_TEMPLATE,
    ],
)



MasterTests = buildSchemaTest(
    name="MasterTests",
    schema={'$ref': '/v2/types.json#/definitions/master'},
    failingInstances=_FAILING_NODENAMES,
    passingInstances=_PASSING_NODENAMES,
)



SlavesTests = buildSchemaTest(
    name="SlavesTests",
    schema={'$ref': '/v2/types.json#/definitions/slaves'},
    failingInstances=[
        # Not arrays.
        None, False, 14, {}, "foo",

        # Arrays with some valid elements but some invalid elements.
        [_PASSING_NODENAMES[0], _FAILING_NODENAMES[0]],
    ] + zip(_FAILING_NODENAMES),
    passingInstances=[
        # Notice this is a single instance which is a list of valid nodenames.
        _PASSING_NODENAMES,
    ],
)



HumanNameTests = buildSchemaTest(
    name='HumanNameTests',
    schema={'$ref': '/v2/types.json#/definitions/website_id'},
    failingInstances=[1, False, None, [], {}, 2.3],
    passingInstances=["John", u"\N{SNOWMAN}"],
)



StorageEngineTests = buildSchemaTest(
    name="StorageEngineTests",
    schema={'$ref': '/v2/types.json#/definitions/storage_engine'},
    failingInstances=[1, False, None, [], {}, 2.3, "abc"],
    passingInstances=["innodb", "myisam"]
)



WebsiteCreateInputTests = buildSchemaTest(
    name='WebsiteCreateInputTests',
    schema={'$ref': '/v2/endpoints.json#/definitions/website/create/input'},
    failingInstances=[
        # Not objects.
        10, "foo", [{}],

        # Missing the required routes property.
        {},

        # Has routes that don't validate.
        {"routes": [{"realm": "hostname", "hostname": 0}]},

        # Has extra properties not defined by the schema.
        {"foo": "bar", "routes": []},

        # Has an owner that doesn't validate.
        {"owner": 10, "routes": []},

        # Has credentials that don't validate.
        {"credentials": [20], "routes": []},

        # Has a template that doesn't validate.
        {"template": False, "routes": []},

        # Insufficient number of routes:
        {"routes": []},

    ],
    passingInstances=[
        {"routes": [{"realm": "hostname", "hostname": "foo"}]},
        {"owner": "abc", "routes": [{"realm": "hostname", "hostname": "foo"}]},
        {"credentials": [{"password": "secret"}],
         "routes": [{"realm": "hostname", "hostname": "foo"}]},
        {"template": {"name": "seaside"},
         "routes": [{"realm": "hostname", "hostname": "foo"}]},
    ],
)


_COMPLETE_WEBSITE = {
    "id": "abcd",
    "owner": "wxyz",
    "credentials": [_PASSING_PASSWORD],
    "routes": [_PASSING_HOSTNAME],
    "template": _PASSING_TEMPLATE,
    "master": _PASSING_NODENAMES[0],
    "slaves": _PASSING_NODENAMES[1:],
    "certificate_id": None,
    }
WebsiteCreateOutputTests = buildSchemaTest(
    name='WebsiteCreateOutputTests',
    schema={'$ref': '/v2/endpoints.json#/definitions/website/create/output'},
    failingInstances=[
        # Not objects.
        10,
        "foo",
        [{}],
        ] + [
        # Missing a required field.
        withoutItem(_COMPLETE_WEBSITE, key)
        for key in _COMPLETE_WEBSITE
    ],
    passingInstances=[
        _COMPLETE_WEBSITE,
        withItems(_COMPLETE_WEBSITE, {"certificate_id": None}),
    ],
)



WebsiteUpdateInputTests = buildSchemaTest(
    name='WebsiteUpdateInputTests',
    schema={'$ref': '/v2/endpoints.json#/definitions/website/update/input'},
    failingInstances=[
        # Not objects.
        10,
        "foo",
        [{}],

        # Tries to update properties that may not be updated.
        {"madeup": "foo"},
        {"id": "abcd"},
        {"owner": "efgh"},
        {"credentials": []},
        {"routes": []},
        {"template": {"name": "seaside"}},
        {"slaves": []},

        # Tries to update properties that *may* be updated together with
        # properties that may not be.
        {"master": _PASSING_NODENAMES[0], "madeup": "foo"},
        {"master": _PASSING_NODENAMES[0], "id": "abcd"},
        {"locked": _PASSING_NODENAMES[0], "madeup": "foo"},
        {"locked": _PASSING_NODENAMES[0], "id": "abcd"},

        # Has a value with the wrong type.
        {"master": None},
        {"master": {}},
        {"master": 3},
        {"locked": {}},
        {"locked": 3},

        # Has an invalid value.
        {"master": "junk"},
        {"locked": "junk"},
    ],
    passingInstances=[
        {"master": _PASSING_NODENAMES[0]},
        {"locked": _PASSING_NODENAMES[0]},
        {"master": _PASSING_NODENAMES[0], "locked": _PASSING_NODENAMES[0]},
        {"locked": None},
    ],
)

WebsiteUpdateOutputTests = buildSchemaTest(
    name='WebsiteUpdateOutputTests',
    schema={'$ref': '/v2/endpoints.json#/definitions/website/update/output'},
    failingInstances=WebsiteCreateOutputTests.failingInstances,
    passingInstances=WebsiteCreateOutputTests.passingInstances,
)


WebsiteDeleteOutputTests = buildSchemaTest(
    name='WebsiteDeleteOutputTests',
    schema={'$ref': '/v2/endpoints.json#/definitions/website/delete/output'},
    failingInstances=[
        # Not null
        {}, [], "", 0,
    ],
    passingInstances=[
        None,
    ]
)


_COMPLETE_INPUT_MAILBOX = {
    "owner": "wxyz",
    "credentials": [_PASSING_PASSWORD],
    "routes": [_PASSING_EMAIL_ADDRESS],
    "given_name": "Aardvark",
    "family_name": "Zebra",
    }

MailboxCreateInputTests = buildSchemaTest(
    name='MailboxCreateInputTests',
    schema={'$ref': '/v2/endpoints.json#/definitions/mailbox/create/input'},
    failingInstances=[
        # Not objects.
        10, "foo", [{}],

        # Missing the required routes property.
        {},

        # Has routes that don't validate.
        withItems(_COMPLETE_INPUT_MAILBOX,
                  {"routes": [{"realm": "hostname", "hostname": 0}]}),

        # Has extra properties not defined by the schema.
        withItems(_COMPLETE_INPUT_MAILBOX, {"foo": "bar"}),

        # Has an owner that doesn't validate.
        withItems(_COMPLETE_INPUT_MAILBOX, {"owner": 10}),

        # Has credentials that don't validate.
        withItems(_COMPLETE_INPUT_MAILBOX, {"credentials": [20]}),

        # Has names that don't validate:
        withItems(_COMPLETE_INPUT_MAILBOX, {"given_name": 20}),
        withItems(_COMPLETE_INPUT_MAILBOX, {"family_name": 20}),
    ],
    passingInstances=[
        _COMPLETE_INPUT_MAILBOX,
        # Owner is optional:
        withoutItem(_COMPLETE_INPUT_MAILBOX, "owner"),
    ],
)

_MINIMAL_MAILBOX = {
    "id": "abc",
    "owner": "wxyz",
    "routes": [_PASSING_EMAIL_ADDRESS],
    }

_COMPLETE_MAILBOX = withItems(_MINIMAL_MAILBOX, {
        "given_name": "Aardvark",
        "family_name": "Zebra",
        })

MailboxCreateOutputTests = buildSchemaTest(
    name='MailboxCreateOutputTests',
    schema={'$ref': '/v2/endpoints.json#/definitions/mailbox/create/output'},
    failingInstances=[
        # Not objects.
        10,
        "foo",
        [{}],
        ] + [
        # Missing a required field.
        withoutItem(_MINIMAL_MAILBOX, key)
        for key in _MINIMAL_MAILBOX
    ],
    passingInstances=[
        _MINIMAL_MAILBOX,
        _COMPLETE_MAILBOX,
    ],
)



_INPUT_DATABASE = dict(
    routes=[_PASSING_DATABASE_ADDRESS],
    credentials=[_PASSING_PASSWORD],
    storage_engine="myisam",
    website_id="123",
    owner="1")

DatabaseCreateInputTests = buildSchemaTest(
    name='DatabaseCreateInputTests',
    schema={'$ref': '/v2/endpoints.json#/definitions/database/create/input'},
    failingInstances=[
        # Not objects.
        10, "foo", [{}],

        # Missing the required routes property.
        {},

        # Has routes that don't validate.
        withItems(_INPUT_DATABASE,
                  {"routes": [{"realm": "mysql"}]}),
        withItems(_INPUT_DATABASE,
                  {"routes": [{"realm": "hostname", "hostname": "www"}]}),

        # Has extra properties not defined by the schema.
        withItems(_INPUT_DATABASE, {"foo": "bar"}),

        # Has an owner that doesn't validate.
        withItems(_INPUT_DATABASE, {"owner": 10}),

        # Has credentials that don't validate.
        withItems(_INPUT_DATABASE, {"credentials": [20]}),

        # Has values that don't validate:
        withItems(_INPUT_DATABASE, {"storage_engine": "XXX"}),
        withItems(_INPUT_DATABASE, {"website_id": 20}),
    ],
    passingInstances=[
        _INPUT_DATABASE,
        # Owner is optional:
        withoutItem(_INPUT_DATABASE, "owner"),
    ],
)



_MINIMAL_DATABASE = {
    "id": "123",
    "owner": "456",
    "routes": [_PASSING_DATABASE_ADDRESS],
    "storage_engine": "myisam",
    "website_id": "123",
    "master": _PASSING_NODENAMES[0],
    "slaves": _PASSING_NODENAMES[1:],
    }


DatabaseCreateOutputTests = buildSchemaTest(
    name='DatabaseCreateOutputTests',
    schema={'$ref': '/v2/endpoints.json#/definitions/database/create/output'},
    failingInstances=[
        # Not objects.
        10,
        "foo",
        [{}],
        ] + [
        # Missing a required field.
        withoutItem(_MINIMAL_DATABASE, key)
        for key in _MINIMAL_DATABASE
    ],
    passingInstances=[
        _MINIMAL_DATABASE,
    ],
)



DatabaseUpdateInputTests = buildSchemaTest(
    name='DatabaseUpdateInputTests',
    schema={'$ref': '/v2/endpoints.json#/definitions/database/update/input'},
    failingInstances=[
        # Not objects.
        10,
        "foo",
        [{}],

        # Tries to update properties that may not be updated.
        {"id": "abcd"},
        {"owner": "efgh"},
        {"credentials": []},
        {"routes": []},
        {"storage_engine": "myisam"},

        # Tries to update properties that *may* be updated together with
        # properties that may not be.
        {"master": _PASSING_NODENAMES[0], "madeup": "foo"},
        {"master": _PASSING_NODENAMES[0], "id": "abcd"},

        # Has a value with the wrong type.
        {"master": None},
        {"master": {}},
        {"master": 3},

        # Has an invalid value.
        {"master": "junk"},
    ],
    passingInstances=[
        {"master": _PASSING_NODENAMES[0]},
        {},
    ],
)



_GOOD_PAGED_BASE = [{'direction': 'ascending',
                     'inclusive': True,
                     'limit': 100,
                     'position': None,
                     'sort': 'xxx',
                     'data': [],
                     },
                    {'direction': 'descending',
                     'inclusive': False,
                     'limit': 20,
                     'position': 1,
                     'sort': 'xxx',
                     'data': []},
                    {'direction': 'descending',
                     'inclusive': False,
                     'limit': 20,
                     'position': "abc",
                     'sort': 'xxx',
                     'data': []}]

PagedBaseOutputTests = buildSchemaTest(
    name='PagedBaseOutputTests',
    schema={'$ref': '/v2/endpoints.json#/definitions/pagedbase'},
    failingInstances=([
        # Not objects.
        10,
        "foo",
        [{}],
        [10],
        ["foo"],
        ] +
        # Missing a required field.
        [[withoutItem(_GOOD_PAGED_BASE[0], key)]
         for key in _GOOD_PAGED_BASE[0]] +
        # Bad values:
        [withItems(_GOOD_PAGED_BASE[0], {"direction": "xxx"}),
         withItems(_GOOD_PAGED_BASE[0], {"inclusive": "xxx"}),
         withItems(_GOOD_PAGED_BASE[0], {"limit": "xxx"}),
         withItems(_GOOD_PAGED_BASE[0], {"position": []}),
         withItems(_GOOD_PAGED_BASE[0], {"sort": 123}),
         withItems(_GOOD_PAGED_BASE[0], {"data": "xxx"})]
    ),
    passingInstances=_GOOD_PAGED_BASE,
)



def buildPagedSchemaTest(name, schema, goodInstance):
    """
    Build a L{TestCase} suitable for testing a schema that extends the
    I{pagedbase} schema, e.g. listing all mailboxes.

    @param name: Name of test case to create
    @type name: L{str}

    @param schema: Schema to test
    @type schema: L{dict}

    @param goodInstance: A good instance of the entity that will be returned in
        the C{data} array, e.g. a mailbox description.
    @type goodInstance: L{dict}

    @return The test case.
    @rtype: A L{SynchronousTestCase} subclass.
    """
    passingInstances = [withItems(base, {'data': [goodInstance]}) for base in
                        _GOOD_PAGED_BASE]
    failingInstances = (
        # Missing data and bad paging info:
        PagedBaseOutputTests.failingInstances +
        # Good paging info, bad data:
        [withItems(_GOOD_PAGED_BASE[0],
                   {'data': [withoutItem(goodInstance, key)]})
         for key in goodInstance] +
        # Missing required key, otherwise fine:
        [withoutItem(passingInstances[0], key) for key in passingInstances[0]] +
        # Extra key:
        [withItems(passingInstances[0], {"extra": "key"})]
        )
    return buildSchemaTest(name, schema, failingInstances=failingInstances,
                           passingInstances=passingInstances)



MailboxListTests = buildPagedSchemaTest(
    name="MailboxListTests",
    schema={"$ref": '/v2/endpoints.json#/definitions/mailbox/list/output'},
    goodInstance=_MINIMAL_MAILBOX)



WebsiteListTests = buildPagedSchemaTest(
    name="WebsiteListTests",
    schema={"$ref": '/v2/endpoints.json#/definitions/website/list/output'},
    goodInstance=_COMPLETE_WEBSITE)



DatabaseListTests = buildPagedSchemaTest(
    name="DatabaseListTests",
    schema={"$ref": '/v2/endpoints.json#/definitions/database/list/output'},
    goodInstance=_MINIMAL_DATABASE)



_MINIMAL_CREATE_CERTIFICATE = dict(
    websites=['100'],
    key='KEY',
    certificate='--- CERT --- ',
    certificate_chain='--- CERT CHAIN---',
)
_COMPLETE_CREATE_CERTIFICATE = withItems(
    _MINIMAL_CREATE_CERTIFICATE, {"owner": "123"})

CertificateCreateInputTests = buildSchemaTest(
    name='CertificateCreateInputTests',
    schema={'$ref': '/v2/endpoints.json#/definitions/certificate/create/input'},
    failingInstances=[
        # Extra attribute:
        withItems(_MINIMAL_CREATE_CERTIFICATE, {"extra": "thing"}),
        # Wrong types:
        withItems(_MINIMAL_CREATE_CERTIFICATE, {"owner": []}),
        withItems(_MINIMAL_CREATE_CERTIFICATE, {"websites": "123"}),
        withItems(_MINIMAL_CREATE_CERTIFICATE, {"key": []}),
        withItems(_MINIMAL_CREATE_CERTIFICATE, {"certificate": []}),
        withItems(_MINIMAL_CREATE_CERTIFICATE, {"certificate_chain": []}),
        # Too many websites:
        withItems(_MINIMAL_CREATE_CERTIFICATE, {"websites": ["123", "456"]}),
        # Too few websites:
        withItems(_MINIMAL_CREATE_CERTIFICATE, {"websites": []}),
        ] + [
        # Missing attributes
        withoutItem(_MINIMAL_CREATE_CERTIFICATE, key)
        for key in _MINIMAL_CREATE_CERTIFICATE
    ],
    passingInstances=[_MINIMAL_CREATE_CERTIFICATE,
                      _COMPLETE_CREATE_CERTIFICATE,
                      withItems(_MINIMAL_CREATE_CERTIFICATE,
                                {"certificate_chain": None})]
)



_MINIMAL_CERTIFICATE = dict(
    id='123',
    owner='346',
    websites=['100'],
    certificate='--- CERT --- ',
    certificate_chain='--- CERT CHAIN---',
)

CertificateCreateOutputTests = buildSchemaTest(
    name='CertificateCreateOutputTests',
    schema={'$ref': '/v2/endpoints.json#/definitions/certificate/create/output'},
    failingInstances=[
        # Not objects.
        10,
        "foo",
        [{}],
        # Extra attribute
        withItems(_MINIMAL_CERTIFICATE, {"extra": "attrib"}),
        ] + [
        # Missing a required field.
        withoutItem(_MINIMAL_CERTIFICATE, key)
        for key in _MINIMAL_CERTIFICATE
    ],
    passingInstances=[
        _MINIMAL_CERTIFICATE,
        withItems(_MINIMAL_CERTIFICATE,
                  {"certificate_chain": None}),
    ],
)



CertificateDeleteOutputTests = buildSchemaTest(
    name='CertificateDeleteOutputTests',
    schema={'$ref': '/v2/endpoints.json#/definitions/certificate/delete/output'},
    failingInstances=[
        # Not null
        {}, [], "", 0,
    ],
    passingInstances=[
        None,
    ]
)



CertificateListTests = buildPagedSchemaTest(
    name="CertificateListTests",
    schema={"$ref": '/v2/endpoints.json#/definitions/certificate/list/output'},
    goodInstance=_MINIMAL_CERTIFICATE)

# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Tests for ``flocker.restapi.docs.publicapi``.
"""

from yaml import safe_dump

from twisted.python.filepath import FilePath
from twisted.trial.unittest import SynchronousTestCase
from twisted.python.reflect import namedModule

from klein import Klein

try:
    namedModule("sphinxcontrib")
    namedModule("sphinx")
    namedModule("docutils")
except ImportError:
    skip = "Sphinx not installed."
else:
    from sphinx.errors import SphinxError

    from ..publicapi import (
        Example, KleinRoute, getRoutes, _loadExamples, _formatExample, makeRst)

from ..._infrastructure import user_documentation, structured, private_api


class GetRoutesTests(SynchronousTestCase):
    """
    Tests for L{getRoutes}.
    """

    def test_routes(self):
        """
        L{getRoutes} returns all the defined routes and their attributes.
        """
        app = Klein()

        def f():
            pass
        f.attr = "attr"

        def g():
            pass
        g.attr = "G"
        app.route(b"/", methods=[b"GET"])(f)
        app.route(b"/g", methods=[b"PUT", b"OPTIONS"])(g)

        routes = sorted(getRoutes(app))
        self.assertEqual(routes, [
            KleinRoute(methods={b"GET"}, path=b"/", endpoint="f",
                       attributes={'attr': 'attr'}),
            KleinRoute(methods={b'PUT', b'OPTIONS'}, path=b'/g', endpoint='g',
                       attributes={'attr': 'G'})])


class MakeRstTests(SynchronousTestCase):
    """
    Tests for L{makeRst}.
    """
    def test_must_be_documented(self):
        """
        If any route doesn't have documentation, then ``SphinxError`` is
        raised.
        """
        app = Klein()

        @app.route(b"/", methods=[b"GET"])
        def f():
            """
            Developer docs.
            """

        self.assertRaises(
            SphinxError,
            lambda: list(makeRst(b"/prefix", 'section', app, None, {})))

    def test_sections(self):
        """
        Documentation is only generated for routes from the corresponding
        section.
        """
        app = Klein()

        @app.route(b"/", methods=[b"GET"])
        @user_documentation(
            u"Undocumented.", header=u"Header", section=u'other-section')
        def f():
            """
            Developer docs.
            """

        @app.route(b"/", methods=[b"GET"])
        @user_documentation(
            u"Documented.", header=u"Header", section=u'section')
        def g():
            """
            Developer docs.
            """

        rest = list(makeRst(b"/prefix", 'section', app, None, {}))

        self.assertEqual(rest, [
            'Header',
            '------',
            '',
            '',
            '.. http:get:: /prefix/',
            '',
            '   Documented.',
            '   ',
            '',
            ])

    def test_stuff(self):
        """
        L{makeRst} returns a generator that returns a bunch of lines of rest.
        """
        app = Klein()

        @app.route(b"/g", methods=[b"PUT"])
        @user_documentation(
            u"""
            Does G-like stuff.

            Like g, G and gg.
            """,
            header=u'g stuff',
            section=u'section')
        def g():
            pass

        rest = list(makeRst(b"/prefix", 'section', app, None, {}))

        self.assertEqual(rest, [
            'g stuff',
            '-------',
            '',
            '',
            '.. http:put:: /prefix/g',
            '',
            '   Does G-like stuff.',
            '   ',
            '   Like g, G and gg.',
            '   ',
            '',
            ])

    def test_private_not_visible(self):
        """
        When an endpoint is decorated with ``@private_api`` it is
        omitted from result of ``makeRst``.
        """
        app = Klein()

        @private_api
        def g():
            pass

        app.route(b"/g", methods=[b"GET"])(g)
        rest = list(makeRst(b"/", "section", app, None, {}))
        self.assertEqual(rest, [])

    def test_example(self):
        """
        When the endpoint being documented references an example HTTP session
        that session is included in the generated API documentation, marked up
        as HTTP.
        """
        app = Klein()

        @app.route("/", methods=["GET"])
        @user_documentation(
            u"""
            Demonstrates examples.
            """, examples=[u"example-example"],
            header=u"Header",
            section=u'section')
        def hasExamples():
            pass

        examples = {
            u"example-example": {
                u"id": u"example-example",
                u"doc": u"This example demonstrates examples.",
                u"request":
                    u"GET /prefix/ HTTP/1.1\n"
                    u"\n",
                u"response":
                    u"HTTP/1.1 200 OK\n"
                    u"\n"
                    u'"%(DOMAIN)s"\n',
                },
            }

        rest = list(makeRst(b"/prefix", 'section', app, examples.get, {}))
        self.assertEqual(
            [u'Header',
             u'------',
             u'',
             u'',
             # This line introduces the endpoint
             '.. http:get:: /prefix/',
             '',
             # Here is the prose documentation for the endpoint.
             '   Demonstrates examples.',
             '   ',
             '   **Example:** This example demonstrates examples.',
             '   ',
             # This is a header introducing the request portion of the session.
             '   Request',
             # This blank line is necessary to satisfy reST for some reason.
             '   ',
             '   .. sourcecode:: http',
             '   ',
             # Here's the bytes of the HTTP request.
             '      GET /prefix/ HTTP/1.1',
             '      Host: api.example.com',
             '      Content-Type: application/json',
             '      ',
             # This blank line is necessary to satisfy reST for some reason.
             '   ',
             # The same again but for the HTTP response.
             '   Response',
             '   ',
             '   .. sourcecode:: http',
             '   ',
             '      HTTP/1.1 200 OK',
             '      Content-Type: application/json',
             '      ',
             '      "example.com"',
             '   ',
             '',
             ], rest)

    INPUT_SCHEMAS = {
        b'/v0/test.json': {
            'endpoint': {
                'type': 'object',
                'properties': {
                    'param': {'$ref': 'test.json#/type'},
                    'optional': {'$ref': 'test.json#/type'},
                },
                'required': ['param'],
            },
            'type': {
                'title': 'TITLE',
                'description': 'one\ntwo',
                'type': 'string',
            },
        }}

    def test_inputSchema(self):
        """
        The generated API documentation includes the input schema.
        """
        app = Klein()

        @app.route(b"/", methods=[b"GET"])
        @structured(
            inputSchema={'$ref': '/v0/test.json#/endpoint'},
            outputSchema={},
            schema_store=self.INPUT_SCHEMAS,
        )
        @user_documentation(
            u"Undocumented.", header=u"Header", section=u'section')
        def f():
            """
            Developer docs,
            """

        rest = list(makeRst(
            b"/prefix", 'section', app, None, self.INPUT_SCHEMAS))

        self.assertEqual(rest, [
            u'Header',
            u'------',
            u'',
            u'',
            '.. http:get:: /prefix/',
            '',
            '   Undocumented.',
            '   ',
            '   .. hidden-code-block:: json',
            '       :label: + Request JSON Schema',
            '       :starthidden: True',
            '   ',
            '       {',
            '           "$schema": "http://json-schema.org/draft-04/schema#",',
            '           "properties": {',
            '               "optional": {',
            '                   "description": "one\\ntwo",',
            '                   "title": "TITLE",',
            '                   "type": "string"',
            '               },',
            '               "param": {',
            '                   "description": "one\\ntwo",',
            '                   "title": "TITLE",',
            '                   "type": "string"',
            '               }',
            '           },',
            '           "required": [',
            '               "param"',
            '           ],',
            '           "type": "object"',
            '       }',
            '   ',
            # YAML is unorderd :(
            '   :<json string optional: TITLE',
            '   ',
            '      one',
            '      two',
            '      ',
            '   :<json string param: *(required)* TITLE',
            '   ',
            '      one',
            '      two',
            '      ',
            '',
            ])

    INPUT_ARRAY_SCHEMAS = {
        b'/v0/test.json': {
            'endpoint': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'param': {'$ref': 'test.json#/type'},
                    },
                    'required': ['param'],
                }
            },
            'type': {
                'title': 'TITLE',
                'description': 'one\ntwo',
                'type': 'string',
            },
        }}

    def test_inputArraySchema(self):
        """
        The generated API documentation includes the input schema if it's an
        array of objects.
        """
        app = Klein()

        @app.route(b"/", methods=[b"GET"])
        @structured(
            inputSchema={'$ref': '/v0/test.json#/endpoint'},
            outputSchema={},
            schema_store=self.INPUT_ARRAY_SCHEMAS,
        )
        @user_documentation(
            u"Undocumented.", header=u"Header", section=u'section')
        def f():
            """
            Developer docs,
            """

        rest = list(makeRst(
            b"/prefix", 'section', app, None, self.INPUT_ARRAY_SCHEMAS))

        self.assertListEqual(rest, [
            u'Header',
            u'------',
            u'',
            u'',
            '.. http:get:: /prefix/',
            '',
            '   Undocumented.',
            '   ',
            '   .. hidden-code-block:: json',
            '       :label: + Request JSON Schema',
            '       :starthidden: True',
            '   ',
            '       {',
            '           "$schema": "http://json-schema.org/draft-04/schema#",',
            '           "items": {',
            '               "properties": {',
            '                   "param": {',
            '                       "description": "one\\ntwo",',
            '                       "title": "TITLE",',
            '                       "type": "string"',
            '                   }',
            '               },',
            '               "required": [',
            '                   "param"',
            '               ],',
            '               "type": "object"',
            '           },',
            '           "type": "array"',
            '       }',
            '   ',
            '   :<jsonarr string param: *(required)* TITLE',
            '   ',
            '      one',
            '      two',
            '      ',
            '',
            ])

    OUTPUT_SCHEMAS = {
        b'/v0/test.json': {
            'endpoint': {
                'type': 'object',
                'properties': {
                    'param': {'$ref': '#/type'},
                },
                'required': ['param'],
            },
            'type': {
                'title': 'TITLE',
                'description': 'one\ntwo',
                'type': 'integer',
            },
        }}

    def test_outputSchema(self):
        """
        The generated API documentation includes the output schema.
        """
        app = Klein()

        @app.route(b"/", methods=[b"GET"])
        @structured(
            inputSchema={},
            outputSchema={'$ref': '/v0/test.json#/endpoint'},
            schema_store=self.OUTPUT_SCHEMAS,
        )
        @user_documentation(
            u"Undocumented.", header=u"Header", section=u'section')
        def f():
            """
            Developer docs,
            """

        rest = list(makeRst(
            b"/prefix", 'section', app, None, self.OUTPUT_SCHEMAS))

        self.assertEqual(rest, [
            u'Header',
            u'------',
            u'',
            u'',
            '.. http:get:: /prefix/',
            '',
            '   Undocumented.',
            '   ',
            '   .. hidden-code-block:: json',
            '       :label: + Response JSON Schema',
            '       :starthidden: True',
            '   ',
            '       {',
            '           "$schema": "http://json-schema.org/draft-04/schema#",',
            '           "properties": {',
            '               "param": {',
            '                   "description": "one\\ntwo",',
            '                   "title": "TITLE",',
            '                   "type": "integer"',
            '               }',
            '           },',
            '           "required": [',
            '               "param"',
            '           ],',
            '           "type": "object"',
            '       }',
            '   ',
            '   :>json integer param: *(required)* TITLE',
            '   ',
            '      one',
            '      two',
            '      ',
            '',
            ])

    OUTPUT_ARRAY_SCHEMAS = {
        b'/v0/test.json': {
            'endpoint': {
                'type': 'array',
                'items': {'$ref': '#/object'},
            },
            'object': {
                'type': 'object',
                'properties': {
                    'param': {'$ref': '#/type'},
                },
                'required': ['param'],
            },
            'type': {
                'title': 'TITLE',
                'description': 'one\ntwo',
                'type': 'integer',
            },
        }}

    def test_outputArraySchema(self):
        """
        The generated API documentation includes the output schema in cases
        where the output is an array.
        """
        app = Klein()

        @app.route(b"/", methods=[b"GET"])
        @structured(
            inputSchema={},
            outputSchema={'$ref': '/v0/test.json#/endpoint'},
            schema_store=self.OUTPUT_ARRAY_SCHEMAS,
        )
        @user_documentation(
            u"Undocumented.", header=u"Header", section=u'section')
        def f():
            """
            Developer docs,
            """

        rest = list(makeRst(
            b"/prefix", 'section', app, None, self.OUTPUT_ARRAY_SCHEMAS))

        self.assertListEqual(rest, [
            u'Header',
            u'------',
            u'',
            u'',
            '.. http:get:: /prefix/',
            '',
            '   Undocumented.',
            '   ',
            '   .. hidden-code-block:: json',
            '       :label: + Response JSON Schema',
            '       :starthidden: True',
            '   ',
            '       {',
            '           "$schema": "http://json-schema.org/draft-04/schema#",',
            '           "items": {',
            '               "properties": {',
            '                   "param": {',
            '                       "description": "one\\ntwo",',
            '                       "title": "TITLE",',
            '                       "type": "integer"',
            '                   }',
            '               },',
            '               "required": [',
            '                   "param"',
            '               ],',
            '               "type": "object"',
            '           },',
            '           "type": "array"',
            '       }',
            '   ',
            '   :>jsonarr integer param: *(required)* TITLE',
            '   ',
            '      one',
            '      two',
            '      ',
            '',
            ])

    INLINED_SCHEMAS = {
        b'/v0/test.json': {
            'endpoint': {
                'type': 'object',
                'properties': {
                    'param': {
                        'title': 'TITLE',
                        'description': 'one\ntwo',
                        'type': 'integer',
                    },
                },
                'required': ['param'],
            },
        }}

    def test_inlinePropertyInSchema(self):
        """
        The generated API documentation support JSON schemas with inlined
        properties.
        """
        app = Klein()

        @app.route(b"/", methods=[b"GET"])
        @structured(
            inputSchema={},
            outputSchema={'$ref': '/v0/test.json#/endpoint'},
            schema_store=self.INLINED_SCHEMAS,
        )
        @user_documentation(
            u"Undocumented.", header=u"Header", section=u'section')
        def f():
            """
            Developer docs,
            """

        rest = list(makeRst(
            b"/prefix", 'section', app, None, self.OUTPUT_SCHEMAS))

        self.assertEqual(rest, [
            u'Header',
            u'------',
            u'',
            u'',
            '.. http:get:: /prefix/',
            '',
            '   Undocumented.',
            '   ',
            '   .. hidden-code-block:: json',
            '       :label: + Response JSON Schema',
            '       :starthidden: True',
            '   ',
            '       {',
            '           "$schema": "http://json-schema.org/draft-04/schema#",',
            '           "properties": {',
            '               "param": {',
            '                   "description": "one\\ntwo",',
            '                   "title": "TITLE",',
            '                   "type": "integer"',
            '               }',
            '           },',
            '           "required": [',
            '               "param"',
            '           ],',
            '           "type": "object"',
            '       }',
            '   ',
            '   :>json integer param: *(required)* TITLE',
            '   ',
            '      one',
            '      two',
            '      ',
            '',
            ])


class FormatExampleTests(SynchronousTestCase):
    """
    Tests for L{_formatExample}.
    """
    def test_requestAndResponse(self):
        """
        L{_formatExample} yields L{unicode} instances representing the lines of
        a reST document describing an example HTTP session.
        """
        example = Example(
            request=b"GET FOO",
            response=b"200 OK",
            doc=u"Documentation of some example."
        )
        lines = list(_formatExample(example, {u"DOMAIN": u"example.com"}))
        self.assertEqual(
            [u'**Example:** Documentation of some example.',
             u'',
             u'Request',
             u'',
             u'.. sourcecode:: http',
             u'',
             u'   GET FOO',
             u'   Host: api.example.com',
             u'   Content-Type: application/json',
             u'',
             u'Response',
             u'',
             u'.. sourcecode:: http',
             u'',
             u'   200 OK',
             u'   Content-Type: application/json',
             u''], lines)

    def test_substitution(self):
        """
        L{_formatExample} replaces I{%(FOO)s}-style variables with values from
        the substitutions dictionary passed to it.
        """
        substitutions = {
            u"DOMAIN": u"example.com",
            u"PATH": u"/some/path",
            u"CODE": u"4242"}
        request = b"GET %(PATH)s HTTP/1.1"
        response = b"HTTP/1.1 %(CODE)s Ok"
        example = Example(
            request=request,
            response=response,
            doc=u'Documentation of some example.'
        )
        lines = list(_formatExample(example, substitutions))
        self.assertEqual(
            [u'**Example:** Documentation of some example.',
             u'',
             u'Request',
             u'',
             u'.. sourcecode:: http',
             u'',
             u'   GET /some/path HTTP/1.1',
             u'   Host: api.example.com',
             u'   Content-Type: application/json',
             u'',
             u'Response',
             u'',
             u'.. sourcecode:: http',
             u'',
             u'   HTTP/1.1 4242 Ok',
             u'   Content-Type: application/json',
             u''], lines)


class LoadExamplesTests(SynchronousTestCase):
    """
    Tests for L{_loadExamples}.
    """
    def test_loaded(self):
        """
        The examples are loaded into a L{dict} mapping example identifiers to
        example L{dict}s.
        """
        foo = {u"id": u"foo", u"foo_value": True}
        bar = {u"id": u"bar", u"bar_value": False}
        path = FilePath(self.mktemp())
        path.setContent(safe_dump([foo, bar]))
        examples = _loadExamples(path)
        self.assertEqual({foo[u"id"]: foo, bar[u"id"]: bar}, examples)

    def test_duplicate(self):
        """
        L{_loadExamples} raises L{Exception} if an id is used by more than one
        example.
        """
        foo = {u"id": u"foo", u"foo_value": True}
        bar = {u"id": u"bar", u"bar_value": False}
        path = FilePath(self.mktemp())
        path.setContent(safe_dump([foo, foo, bar]))
        self.assertRaises(Exception, _loadExamples, path)


class VariableInterpolationTests(SynchronousTestCase):
    """
    Tests for interpolation into route bodies done by L{makeRst}.
    """
    def test_node_substitution(self):
        """
        A fake hostname is substituted for I{NODE_0} in the route body.
        """
        example = dict(
            request=(
                "GET / HTTP/1.1\n"
                "\n"
                "%(NODE_0)s\n"
            ),
            response=(
                "HTTP/1.1 200 OK\n"
                "\n"
            ),
            doc=u"Documentation of some example."
        )
        app = Klein()

        @app.route(b"/", methods=[b"GET"])
        @user_documentation(
            u"", examples=[u"dummy id"], header=u"Header", section=u'section')
        def f():
            pass

        rst = makeRst(
            b"/prefix", 'section', app, lambda identifier: example, {})
        self.assertEqual(
            # Unfortunately a lot of stuff that's not relevant to this test
            # comes back from makeRst.
            [u'Header',
             u'------',
             u'',
             u'',
             u'.. http:get:: /prefix/',
             u'',
             u'   **Example:** Documentation of some example.',
             u'   ',
             u'   Request',
             u'   ',
             u'   .. sourcecode:: http',
             u'   ',
             u'      GET / HTTP/1.1',
             u'      Host: api.example.com',
             u'      Content-Type: application/json',
             u'      ',
             # Here is the important line.
             u'      cf0f0346-17b2-4812-beca-1434997d6c3f',
             u'   ',
             u'   Response',
             u'   ',
             u'   .. sourcecode:: http',
             u'   ',
             u'      HTTP/1.1 200 OK',
             u'      Content-Type: application/json',
             u'      ',
             u'   ',
             u''],
            list(rst)
        )


class ExampleFromDictionaryTests(SynchronousTestCase):
    """
    Tests for ``Example.fromDictionary``.
    """
    def test_required_arguments(self):
        """
        ``Example.fromDictionary`` requires request and response keys
        in the supplied dictionary and passes them to the Example
        initialiser.
        """
        expected_request = 'GET /v1/some/example/request HTTP/1.1\n'
        expected_response = 'HTTP/1.0 200 OK\n\n'
        expected_doc = u'Documentation for some example.'

        supplied_dictionary = {
            'request': expected_request,
            'response': expected_response,
            'doc': expected_doc,
        }

        expected_example = Example(
            request=expected_request,
            response=expected_response,
            doc=expected_doc,
        )

        self.assertEqual(
            expected_example, Example.fromDictionary(supplied_dictionary))

# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.restapi.docs.test.test_publicapi -*-
"""
Sphinx extension for automatically documenting api endpoints.
"""

from inspect import getsourcefile
from collections import namedtuple
import json

from yaml import safe_load
from docutils import nodes

from sphinxcontrib import httpdomain
from sphinxcontrib.autohttp.flask import translate_werkzeug_rule
from sphinxcontrib.autohttp.common import http_directive

from sphinx.util.compat import Directive
from sphinx.util.nodes import nested_parse_with_titles
from sphinx.util.docstrings import prepare_docstring
from docutils.statemachine import ViewList
from docutils.parsers.rst import directives

from twisted.python.reflect import namedAny
from twisted.python.filepath import FilePath

from .._schema import LocalRefResolver, resolveSchema

# Disable "HTTP Routing Table" index:
httpdomain.HTTPDomain.indices = []


class KleinRoute(namedtuple('KleinRoute', 'path methods endpoint attributes')):
    """
    A L{KleinRoute} instance represents a route in a L{klein.Klein}
    application, along with the metadata associated to the route function.

    @ivar methods: The HTTP methods the route accepts.
    @ivar path: The path of this route.
    @ivar endpoint: The L{werkzeug} endpoint name.
    @ivar attributes: The attributes function associated with this route.
    """


class Example(namedtuple("Example", "request response")):
    """
    An L{Example} instance represents a single HTTP session example.

    @ivar request: The example HTTP request.
    @type request: L{unicode}

    @ivar response: The example HTTP response.
    @type response: L{unicode}
    """
    @classmethod
    def fromDictionary(cls, d):
        """
        Create an L{Example} from a L{dict} with C{u"request"} and
        C{u"response"} keys and L{unicode} values.
        """
        return cls(d[u"request"], d[u"response"])


def getRoutes(app):
    """
    Get the routes assoicated with a L{klein} application.

    @param app: The L{klein} application to introspect.
    @type app: L{klein.Klein}

    @return: The routes associated to the application.
    @rtype: A generator of L{KleinRoute}s
    """
    # This accesses private attributes of Klein:
    # https://github.com/twisted/klein/issues/49
    # Adapted from sphinxcontrib.autohttp.flask
    for rule in app._url_map.iter_rules():
        methods = rule.methods.difference(['HEAD'])
        path = translate_werkzeug_rule(rule.rule)

        # Klein sets `segment_count` which we don't care about
        # so ignore it.
        attributes = vars(app._endpoints[rule.endpoint]).copy()
        if 'segment_count' in attributes:
            del attributes['segment_count']

        yield KleinRoute(
            methods=methods, path=path, endpoint=rule.endpoint,
            attributes=attributes)


def _parseSchema(schema, schema_store):
    """
    Parse a JSON Schema and return some information to document it.

    @param schema: L{dict} representing a JSON Schema.

    @param dict schema_store: A mapping between schema paths
        (e.g. ``b/v1/types.json``) and the JSON schema structure.

    @return: A L{dict} representing the information needed to
        document the schema.
    """
    result = {}

    resolver = LocalRefResolver(
        base_uri=b'',
        referrer=schema, store=schema_store)

    if schema.get(u'$ref') is None:
        raise Exception('Non-$ref top-level definitions not supported.')

    def fill_in_attribute(attr, propSchema):
        attr['title'] = propSchema['title']
        attr['description'] = prepare_docstring(
            propSchema['description'])
        attr['required'] = property in schema.get('required', [])
        attr['type'] = propSchema['type']

    with resolver.resolving(schema[u'$ref']) as schema:
        if schema[u'type'] != u'object':
            raise Exception('Non-object top-level definitions not supported.')

        result['properties'] = {}
        for property, propSchema in schema[u'properties'].iteritems():
            attr = result['properties'][property] = {}
            if "$ref" in propSchema:
                with resolver.resolving(propSchema['$ref']) as propSchema:
                    fill_in_attribute(attr, propSchema)
            else:
                fill_in_attribute(attr, propSchema)
    return result


def _introspectRoute(route, exampleByIdentifier, schema_store):
    """
    Given a L{KleinRoute}, extract the information to generate documentation.

    @param route: Route to inspect
    @type route: L{KleinRoute}

    @param exampleByIdentifier: A one-argument callable that accepts an example
        identifier and returns an HTTP session example.

    @param dict schema_store: A mapping between schema paths
        (e.g. ``b/v1/types.json``) and the JSON schema structure.

    @return: Information about the route
    @rtype: L{dict} with the following keys.
      - C{'description'}:
             L{list} of L{str} containing a prose description of the endpoint.
      - C{'input'} I{(optional)}:
             L{dict} describing the input schema. Has C{'properties'} key with
             a L{list} of L{dict} of L{dict} with keys C{'title'},
             C{'description'} and C{'required'} describing the toplevel
             properties of the schema.
      - C{'input_schema'} I{(optional)}:
             L{dict} including the verbatim input JSON Schema.
      - C{'output'} I{(optional)}:
            see C{'input'}.
      - C{'output_schema'} I{(optional)}:
             L{dict} including the verbatim output JSON Schema.
      - C{'paged'} I{(optional)}:
            If present, the endpoint is paged.
            L{dict} with keys C{'defaultKey'} and C{'otherKeys'} giving the
            names of default and available sort keys.
      - C{'examples'}:
            A list of examples (L{Example} instances) for this endpoint.
    """
    result = {}

    userDocumentation = route.attributes.get(
        "userDocumentation", "Undocumented.")
    result['description'] = prepare_docstring(userDocumentation)

    inputSchema = route.attributes.get('inputSchema', None)
    outputSchema = route.attributes.get('outputSchema', None)
    if inputSchema:
        # _parseSchema doesn't handle all JSON Schema yet
        # Fail softly by simply not including the documentation
        # for it.
        # https://clusterhq.atlassian.net/browse/FLOC-1171
        try:
            result['input'] = _parseSchema(inputSchema, schema_store)
        except:
            pass
        result["input_schema"] = inputSchema

    if outputSchema:
        # See above
        # https://clusterhq.atlassian.net/browse/FLOC-1171
        try:
            result['output'] = _parseSchema(outputSchema, schema_store)
        except:
            pass
        result["output_schema"] = outputSchema

    examples = route.attributes.get("examples") or []
    result['examples'] = list(
        Example.fromDictionary(exampleByIdentifier(identifier))
        for identifier in examples)

    return result


def _formatSchema(data, param):
    """
    Generate the rst associated to a JSON schema.

    @param data: See L{inspectRoute}.
    @param param: rst entity to use for JSON properties.
    @type param: L{str}
    """
    for property, attr in sorted(data[u'properties'].iteritems()):
        if attr['required']:
            required = '*(required)* '
        else:
            required = ''
        yield ':%s %s %s: %s%s' % (param, attr['type'], property, required,
                                   attr['title'])
        yield ''
        for line in attr['description']:
            yield '   ' + line


def _formatActualSchema(schema, title, schema_store):
    """
    Format a schema to reStructuredText.

    :param dict schema: The JSON Schema to validate against.

    :param dict schema_store: A mapping between schema paths
        (e.g. ``b/v1/types.json``) and the JSON schema structure.

    :return: Iterable of strings creating reStructuredText.
    """
    yield ".. hidden-code-block:: json"
    yield "    :label: " + title
    yield "    :starthidden: True"
    yield ""
    schema = resolveSchema(schema, schema_store)
    lines = json.dumps(schema, indent=4, separators=(',', ': '),
                       sort_keys=True).splitlines()
    for line in lines:
        yield "    " + line
    yield ""


def _formatExample(example, substitutions):
    """
    Generate the rst associated with an HTTP session example.

    @param example: An L{Example} to format.

    @param substitutions: A L{dict} to use to interpolate variables in the
        example request and response.

    @return: A generator which yields L{unicode} strings each of which should
        be a line in the resulting rst document.
    """
    yield u"**Example request**"
    yield u""
    yield u".. sourcecode:: http"
    yield u""

    lines = (example.request % substitutions).splitlines()
    lines.insert(1, u"Content-Type: application/json")
    lines.insert(1, u"Host: api.%(DOMAIN)s" % substitutions)
    for line in lines:
        yield u"   " + line.rstrip()
    yield u""

    yield u"**Example response**"
    yield u""
    yield u".. sourcecode:: http"
    yield u""

    lines = (example.response % substitutions).splitlines()
    lines.insert(1, u"Content-Type: application/json")
    for line in lines:
        yield u"   " + line.rstrip()
    yield u""


def _formatRouteBody(data, schema_store):
    """
    Generate the description of a L{klein} route.

    @param data: Result of L{_introspectRoute}.

    @param dict schema_store: A mapping between schema paths
        (e.g. ``b/v1/types.json``) and the JSON schema structure.

    @return: The lines of sphinx representing the generated documentation.
    @rtype: A generator of L{unicode}s.
    """
    baseSubstitutions = {
        u"DOMAIN": u"example.com",
        }

    for line in data['description']:
        yield line

    if 'input' in data:
        for line in _formatActualSchema(data['input_schema'],
                                        "+ Request JSON Schema",
                                        schema_store):
            yield line
    if 'output' in data:
        for line in _formatActualSchema(data['output_schema'],
                                        "+ Response JSON Schema",
                                        schema_store):
            yield line

    for example in data['examples']:
        substitutions = baseSubstitutions.copy()
        for line in _formatExample(example, substitutions):
            yield line

    if 'input' in data:
        # <json is what sphinxcontrib-httpdomain wants to call "json in a
        # request body"
        for line in _formatSchema(data['input'], '<json'):
            yield line

    if 'output' in data:
        # >json is what sphinxcontrib-httpdomain wants to call "json in a
        # response body"
        for line in _formatSchema(data['output'], '>json'):
            yield line


def makeRst(prefix, app, exampleByIdentifier, schema_store):
    """
    Generate the sphinx documentation associated with a L{klein} application.

    @param prefix: The URL prefix of the URLs in this application.
    @type prefix: L{bytes}

    @param app: The L{klein} application to introspect.
    @type app: L{klein.Klein}

    @param exampleByIdentifier: A one-argument callable that accepts an example
        identifier and returns an HTTP session example.

    @param dict schema_store: A mapping between schema paths
        (e.g. ``b/v1/types.json``) and the JSON schema structure.

    @return: The lines of sphinx representing the generated documentation.
    @rtype: A generator of L{str}s.
    """
    # Adapted from sphinxcontrib.autohttp.flask
    for route in sorted(getRoutes(app)):
        data = _introspectRoute(route, exampleByIdentifier, schema_store)
        for method in route.methods:
            body = _formatRouteBody(data, schema_store)
            for line in http_directive(method, prefix + route.path, body):
                yield line


def _loadExamples(path):
    """
    Read the YAML-format HTTP session examples from the file at the given path.

    @type path: L{FilePath}

    @raise Exception: If any example identifier is used more than once.

    @return: A L{dict} mapping example identifiers to example L{dict}s.
    """
    # Load all of the examples so they're available for the loader when we
    # get there.
    examplesRaw = safe_load(path.getContent())
    examplesMap = dict(
        (example["id"], example)
        for example in examplesRaw)

    # Avoid duplicate identifiers.
    if len(examplesRaw) != len(examplesMap):
        identifiers = [example["id"] for example in examplesRaw]
        duplicates = list(
            identifier
            for (index, identifier)
            in enumerate(identifiers)
            if identifiers.index(identifier) != index)
        raise Exception(
            "Duplicate identifiers in example file: %r" % (duplicates,))
    return examplesMap


class AutoKleinDirective(Directive):
    """
    Implementation of the C{autoklein} directive.
    """
    has_content = True
    required_arguments = 1

    option_spec = {
        # The URL prefix of the URLs in this application.
        'prefix': directives.unchanged,
        # Path to examples YAML file, relative to document which includes
        # the directive. Using just passed in path is no good, since it's
        # relative to sphinx-build working directory which may vary.
        'examples_path': directives.unchanged,
        # Python import path of schema store.
        'schema_store_fqpn': directives.unchanged}

    def run(self):
        schema_store = namedAny(self.options["schema_store_fqpn"])

        appContainer = namedAny(self.arguments[0])

        # This is the path of the file that contains the autoklein directive.
        src_path = FilePath(self.state_machine.get_source(self.lineno))

        # self.options["examples_path"] is a path relative to the source file
        # containing it to a file containing examples to include.
        examples_path = src_path.parent().preauthChild(
            self.options["examples_path"])

        self._examples = _loadExamples(examples_path)

        # The contents of the example file are included in the output so the
        # example file is a dependency of the document.
        self.state.document.settings.record_dependencies.add(
            examples_path.path)

        # The following three lines record (some?) of the dependencies of the
        # directive, so automatic regeneration happens.

        # Specifically, it records this file, and the file where the app
        # is declared.  If we ever have routes for a single app declared
        # across multiple files, this will need to be updated.
        appFileName = getsourcefile(appContainer)
        self.state.document.settings.record_dependencies.add(appFileName)
        self.state.document.settings.record_dependencies.add(__file__)

        # Copied from sphinxcontrib.autohttp.flask
        # Return the result of parsing the rst f
        node = nodes.section()
        node.document = self.state.document
        result = ViewList()
        restLines = makeRst(
            prefix=self.options['prefix'], app=appContainer.app,
            exampleByIdentifier=self._exampleByIdentifier,
            schema_store=schema_store)
        for line in restLines:
            result.append(line, '<autoklein>')
        nested_parse_with_titles(self.state, result, node)
        return node.children

    def _exampleByIdentifier(self, identifier):
        """
        Get one of the examples defined in the examples file.
        """
        return self._examples[identifier]


def setup(app):
    """
    Entry point for sphinx extension.
    """
    if 'http' not in app.domains:
        httpdomain.setup(app)
    app.add_directive('autoklein', AutoKleinDirective)

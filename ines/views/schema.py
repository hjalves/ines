# -*- coding: utf-8 -*-

from urllib2 import unquote

from colander import All
from colander import Boolean as BaseBoolean
from colander import drop
from colander import Length
from colander import Mapping
from colander import null
from colander import Number
from colander import OneOf
from colander import required
from colander import Sequence
from colander import Tuple
from pyramid.compat import is_nonstr_iter
from pyramid.settings import asbool
from zope.interface import implementer

from ines import DEFAULT_METHODS
from ines.convert import camelcase
from ines.convert import force_unicode
from ines.convert import maybe_list
from ines.interfaces import ISchemaView
from ines.route import lookup_for_route_params
from ines.views.fields import FilterByType
from ines.views.fields import OneOfWithDescription
from ines.utils import MissingDict
from ines.utils import MissingList


@implementer(ISchemaView)
class SchemaView(object):
    def __init__(self, route_name, routes_names, title=None, description=None, model=None):
        self.route_name = route_name
        self.routes_names = routes_names
        self.title = title
        self.description = description
        self.model = model

    def __call__(self, context, request):
        nodes = MissingDict()
        requested_methods = [key.lower() for key in request.GET.keys()]

        types = MissingList()
        models = MissingList()
        for route_name, request_methods in self.routes_names.items():
            route_methods = []
            for request_method in maybe_list(request_methods or DEFAULT_METHODS):
                if not requested_methods or request_method.lower() in requested_methods:
                    route_methods.append(request_method)
            if not route_methods:
                continue

            intr_route = request.registry.introspector.get('routes', route_name)
            if intr_route is None:
                continue
            route = intr_route['object']
            params = dict((k, '{{%s}}' % camelcase(k)) for k in lookup_for_route_params(route))
            url = '%s%s' % (request.application_url, unquote(route.generate(params)))

            schemas = request.registry.config.lookup_input_schema(route_name, route_methods)
            schemas.extend(request.registry.config.lookup_output_schema(route_name, route_methods))
            for schema in schemas:
                fields = []
                if schema.schema:
                    details = self.construct_structure(
                        request,
                        schema.schema,
                        schema.schema_type,
                        types,
                        models)
                    if isinstance(details, dict):
                        fields.append(details)
                    else:
                        fields.extend(details)

                if schema.schema_type == 'request' and schema.fields_schema:
                    details = self.construct_structure(
                        request,
                        schema.fields_schema,
                        schema.schema_type,
                        types,
                        models)
                    if isinstance(details, dict):
                        fields.append(details)
                    else:
                        fields.extend(details)

                name = camelcase('%s_%s' % (schema.request_method, schema.route_name))
                nodes[name][schema.schema_type] = fields
                nodes[name]['method'] = schema.request_method.upper()
                nodes[name]['url'] = url

        nodes['fieldTypes'] = lookup_for_common_fields(types, ignore_key='fieldType')
        nodes['models'] = lookup_for_common_fields(models, ignore_key='model')
        return nodes

    def construct_structure(self, request, schema, schema_type, types, models, parent_name=None):
        if isinstance(schema.typ, Sequence):
            child = schema.children[0]
            if not schema.name:
                schema = child

            name = camelcase(schema.name)
            details = {
                'model': name,
                'type': 'sequence',
                'title': schema.title,
                'description': schema.description or None}
            models[name].append(details)

            # Find and add child
            child_details = self.construct_structure(
                request,
                child,
                schema_type,
                types,
                models,
                parent_name=schema.name)

            if isinstance(details, dict):
                if isinstance(child.typ, Mapping):
                    details['type'] = 'model'
                    details.update(child_details)
                else:
                    details['fields'] = [child_details]
            else:
                details['fields'] = child_details

            return details

        elif isinstance(schema.typ, Tuple):
            raise NotImplementedError('Tuple type need to be implemented')

        elif isinstance(schema.typ, Mapping):
            fields = []
            for child in schema.children:
                fields.append(self.construct_structure(
                    request,
                    child,
                    schema_type,
                    types,
                    models,
                    parent_name=schema.name))

            name = schema.name or parent_name
            if not name:
                return fields

            name = camelcase(name)
            details = {
                'type': 'model',
                'title': schema.title,
                'description': schema.description or None,
                'fields': fields,
                'model': name}
            models[name].append(details)
            return details

        else:
            name = camelcase(schema.name)
            details = {
                'fieldType': name,
                'title': schema.title,
                'description': schema.description or None}
            types[name].append(details)

            if isinstance(schema.typ, FilterByType):
                for cls in schema.typ.__class__.__mro__[1:]:
                    if cls is not FilterByType:
                        details['type'] = str(cls.__name__).lower()
                        break
                details['filter'] = True
            else:
                details['type'] = get_colander_type_name(schema.typ)

            request_validation = []
            if schema.validator:
                if isinstance(schema.validator, All):
                    validators = schema.validator.validators
                elif not is_nonstr_iter(schema.validator):
                    validators = [schema.validator]

                for validator in validators:
                    if isinstance(validator, OneOfWithDescription):
                        details['options'] = []
                        for choice, description in validator.choices_with_descripton:
                            details['options'].append({
                                'value': choice,
                                'text': request.translate(description)})
                    elif isinstance(validator, OneOf):
                        details['options'] = []
                        for choice in validator.choices:
                            choice_description = force_unicode(choice).replace(u'_', u' ').title()
                            details['options'].append({
                                'value': choice,
                                'text': choice_description})
                    else:
                        if isinstance(validator, Length):
                            validation_option = {}
                            if validator.min is not None:
                                validation_option['min'] = validator.min
                            if validator.max is not None:
                                validation_option['max'] = validator.max
                        else:
                            validation_option = True

                        request_validation.append((validator, validation_option))

            if hasattr(schema, 'use_when'):
                details['useWhen'] = dict((camelcase(k), v) for k, v in schema.use_when.items())

            if schema_type == 'request':
                validation = {}
                if schema.required:
                    validation['required'] = True

                if request_validation:
                    for validator, validation_option in request_validation:
                        validation[get_colander_type_name(validator)] = validation_option
                if validation:
                    details['validation'] = validation

                default = schema.missing
            else:
                if schema.missing is drop:
                    details['maybeNotSent'] = True
                default = schema.default

            if (default is not drop
                    and default is not required
                    and default is not null):
                if isinstance(schema.typ, Number):
                    default = schema.typ.num(default)
                elif isinstance(schema.typ, BaseBoolean):
                    default = asbool(default)
                details['default'] = default

            return details


def get_colander_type_name(node):
    return camelcase(str(node.__class__.__name__).lower())


def lookup_for_common_fields(values, ignore_key=None):
    result = MissingDict()
    for name, name_list in values.items():
        if not name_list:
            continue

        for key, value in name_list[0].items():
            if key == ignore_key:
                continue

            the_same = True
            for name_options in name_list[1:]:
                if key not in name_options:
                    the_same = False
                    break

            if the_same:
                result[name][key] = value
                for name_options in name_list:
                    name_options.pop(key)

    return result

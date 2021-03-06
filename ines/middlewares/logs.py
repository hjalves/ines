# -*- coding: utf-8 -*-

import sys
from traceback import format_exception

from pyramid.decorator import reify
from pyramid.httpexceptions import HTTPInternalServerError
from pyramid.interfaces import IRequestFactory

from ines.middlewares import Middleware
from ines.utils import format_error_to_json


class LoggingMiddleware(Middleware):
    name = 'logging'

    @property
    def request_factory(self):
        return self.config.registry.queryUtility(IRequestFactory)

    @reify
    def api_name(self):
        return self.settings.get('logging_api_name') or 'logging'

    def __call__(self, environ, start_response):
        try:
            for chunk in self.application(environ, start_response):
                yield chunk
        except (BaseException, Exception):
            type_, value, tb = sys.exc_info()
            error = ''.join(format_exception(type_, value, tb))

            # Save / log error
            request = self.request_factory(environ)
            request.registry = self.config.registry

            try:
                getattr(request.api, self.api_name).log_critical('internal_server_error', error)
            except (BaseException, Exception):
                print error

            internal_server_error = HTTPInternalServerError()
            headers = [('Content-type', 'application/json')]
            start_response(internal_server_error.status, headers)
            yield format_error_to_json(internal_server_error, request=request)

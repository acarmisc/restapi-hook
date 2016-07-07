# -*- coding: utf-8 -*-
import functools
import json
import os
import pprint

import psutil
import time
import werkzeug
import logging

from openerp import http
from openerp.http import Response, JsonRequest, HttpRequest, request, Root, rpc_request, rpc_response
from openerp.service.server import memory_info

_logger = logging.getLogger(__name__)


def croute(route=None, **kw):

    routing = kw.copy()
    assert 'type' not in routing or routing['type'] in ("http", "json")

    def decorator(f):
        _logger.info('Custom Decorator')
        if route:
            if isinstance(route, list):
                routes = route
            else:
                routes = ['/restapi/' + route]
            routing['routes'] = routes

        @functools.wraps(f)
        def response_wrap(*args, **kw):
            response = f(*args, **kw)
            if isinstance(response, Response) or f.routing_type == 'json':
                return response

            if isinstance(response, basestring):
                return Response(response)

            if isinstance(response, werkzeug.exceptions.HTTPException):
                response = response.get_response(request.httprequest.environ)
            if isinstance(response, werkzeug.wrappers.BaseResponse):
                response = Response.force_type(response)
                response.set_default()
                return response

            _logger.warn("<function %s.%s> returns an invalid response type for an http request" % (
            f.__module__, f.__name__))
            return response

        response_wrap.routing = routing
        response_wrap.original_func = f
        return response_wrap

    return decorator


class CRoot(Root):

    def get_request(self, httprequest):

        # deduce type of request
        if 'restapi' in httprequest.path:
            return CJsonRequest(httprequest)
        if httprequest.args.get('jsonp'):
            return JsonRequest(httprequest)
        if httprequest.mimetype in ("application/json", "application/json-rpc"):
            return JsonRequest(httprequest)
        else:
            return HttpRequest(httprequest)


class CJsonRequest(JsonRequest):
    """ Generalizing to HTTP REST API """

    _request_type = "json"

    def __init__(self, *args):
        super(JsonRequest, self).__init__(*args)

        self.jsonp_handler = None

        args = self.httprequest.args
        jsonp = args.get('jsonp')
        self.jsonp = jsonp
        request = None
        request_id = args.get('id')

        if jsonp and self.httprequest.method == 'POST':
            # jsonp 2 steps step1 POST: save call
            def handler():
                self.session['jsonp_request_%s' % (request_id,)] = self.httprequest.form['r']
                self.session.modified = True
                headers = [('Content-Type', 'text/plain; charset=utf-8')]
                r = werkzeug.wrappers.Response(request_id, headers=headers)
                return r

            self.jsonp_handler = handler
            return
        elif jsonp and args.get('r'):
            # jsonp method GET
            request = args.get('r')
        elif jsonp and request_id:
            # jsonp 2 steps step2 GET: run and return result
            request = self.session.pop('jsonp_request_%s' % (request_id,), '{}')
        else:
            # regular jsonrpc2
            request = self.httprequest.stream.read()

        # Read POST content or POST Form Data named "request"
        self.jsonrequest = {}

        self.params = dict(self.jsonrequest.get("params", {}))
        self.context = self.params.pop('context', dict(self.session.context))

    def _json_response(self, result=None, error=None):
        response = {
            'pagination': result.pagination,
            'msg': result.msg
        }
        if error is not None:
            response['error'] = error
        if result is not None:
            response['payload'] = result.payload

        if self.jsonp:
            # If we use jsonp, that's mean we are called from another host
            # Some browser (IE and Safari) do no allow third party cookies
            # We need then to manage http sessions manually.
            response['session_id'] = self.session_id
            mime = 'application/javascript'
            body = "%s(%s);" % (self.jsonp, json.dumps(response),)
        else:
            mime = 'application/json'
            body = json.dumps(response)

        return Response(
            body, headers=[('Content-Type', mime),
                           ('Content-Length', len(body))])

    def _call_function(self, *args, **kwargs):
        from openerp.service import security, model as service_model
        request = self
        if self.endpoint.routing['type'] != self._request_type:
            msg = "%s, %s: Function declared as capable of handling request of type '%s' but called with a request of type '%s'"
            params = (self.endpoint.original, self.httprequest.path, self.endpoint.routing['type'], self._request_type)
            _logger.info(msg, *params)
            raise werkzeug.exceptions.BadRequest(msg % params)

        if self.endpoint_arguments:
            kwargs.update(self.endpoint_arguments)

        # Backward for 7.0
        if self.endpoint.first_arg_is_req:
            args = (request,) + args

        # Correct exception handling and concurency retry
        @service_model.check
        def checked_call(___dbname, *a, **kw):
            # The decorator can call us more than once if there is an database error. In this
            # case, the request cursor is unusable. Rollback transaction to create a new one.
            if self._cr:
                self._cr.rollback()
                self.env.clear()
            result = self.endpoint(*a, **kw)
            if isinstance(result, Response) and result.is_qweb:
                # Early rendering of lazy responses to benefit from @service_model.check protection
                result.flatten()
            return result

        if self.db:
            return checked_call(self.db, *args, **kwargs)
        return self.endpoint(*args, **kwargs)

    def dispatch(self):
        if self.jsonp_handler:
            return self.jsonp_handler()
        try:
            rpc_request_flag = rpc_request.isEnabledFor(logging.DEBUG)
            rpc_response_flag = rpc_response.isEnabledFor(logging.DEBUG)
            if rpc_request_flag or rpc_response_flag:
                endpoint = self.endpoint.method.__name__
                model = self.params.get('model')
                method = self.params.get('method')
                args = self.params.get('args', [])

                start_time = time.time()
                _, start_vms = 0, 0
                if psutil:
                    _, start_vms = memory_info(psutil.Process(os.getpid()))
                if rpc_request and rpc_response_flag:
                    rpc_request.debug('%s: %s %s, %s',
                                      endpoint, model, method, pprint.pformat(args))

            # Result is an istance of CResponse
            response = self._call_function(**self.params)
            result = response.payload

            if rpc_request_flag or rpc_response_flag:
                end_time = time.time()
                _, end_vms = 0, 0
                if psutil:
                    _, end_vms = memory_info(psutil.Process(os.getpid()))
                logline = '%s: %s %s: time:%.3fs mem: %sk -> %sk (diff: %sk)' % (
                    endpoint, model, method, end_time - start_time, start_vms / 1024, end_vms / 1024,
                    (end_vms - start_vms) / 1024)
                if rpc_response_flag:
                    rpc_response.debug('%s, %s', logline, pprint.pformat(result))
                else:
                    rpc_request.debug(logline)

            return self._json_response(response)
        except Exception, e:
            return self._handle_exception(e)


class CResponse:

    def __init__(self, msg=None, payload=None, status_code=200, pagination=None):
        self.msg = msg
        self.payload = payload
        self.status_code = status_code
        self.pagination = pagination


class RestAPICore(http.Controller):
    pass

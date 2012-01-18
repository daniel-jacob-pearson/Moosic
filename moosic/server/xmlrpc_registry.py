# xmlrpc_registry.py - A method registry for use with xmlrpclib
# Copyright (C) 2001 by Eric Kidd. All rights reserved.
# Modified by Daniel J. Pearson on 24 Feb 2003
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
# 3. The name of the author may not be used to endorse or promote products
#    derived from this software without specific prior written permission. 
#  
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR AND CONTRIBUTORS ``AS IS'' AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
# OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGE.

import sys
import xmlrpclib

# Some type names for use in method signatures.
INT="int"
BOOLEAN="boolean"
DOUBLE="double"
STRING="string"
DATETIME="dateTime.iso8601"
BASE64="base64"
ARRAY="array"
STRUCT="struct"

# Some error codes, borrowed from xmlrpc-c.
INTERNAL_ERROR = -500
TYPE_ERROR = -501
INDEX_ERROR = -502
PARSE_ERROR = -503
NETWORK_ERROR = -504
TIMEOUT_ERROR = -505
NO_SUCH_METHOD_ERROR = -506
REQUEST_REFUSED_ERROR = -507
INTROSPECTION_DISABLED_ERROR = -508
LIMIT_EXCEEDED_ERROR = -509
INVALID_UTF8_ERROR = -510

class Registry:
    """A registry for XML-RPC methods supported by a server.
    This is based on the method registry in xmlrpc-c."""

    def __init__ (self, allow_introspection=1):
        """Create a new method registry."""
        self._allow_introspection = allow_introspection
        self._methods = {}
        self._signatures = {}
        self._help = {}
        self._default_method = None
        self._install_system_methods()

    def _install_system_methods (self):
        """Install the build-in methods in the system.* suite."""
        self.add_method('system.listMethods',
                        self.system_listMethods,
                        [[ARRAY]])
        self.add_method('system.methodSignature',
                        self.system_methodSignature,
                        [[ARRAY, STRING]])
        self.add_method('system.methodHelp',
                        self.system_methodHelp,
                        [[STRING, STRING]])
        self.add_method('system.multicall',
                        self.system_multicall,
                        [[ARRAY, ARRAY]])

    def add_method (self, name, method, signature=None, help=None):
        """Add a method to the registry, with optional documentation
        and signature."""

        # Try to default things sensibly.
        if help is None:
            help = method.__doc__
        if help is None:
            help = ''
        if signature is None:
            signature = 'undef'

        # Install our new method.
        self._methods[name] = method
        self._signatures[name] = signature
        self._help[name] = help

    def register(self, func, signature=None, name=None, help=None):
        if name is None:
            name = func.__name__
        if signature is None and hasattr(func, 'signature'):
            signature = func.signature
        self.add_method(name, func, signature, help)

    def set_default_method (self, method):
        """Set a default method to handle otherwise unsupported requests."""
        self._default_method = method

    def dispatch_call (self, name, params):
        """Dispatch an XML-RPC request, and return the result."""

        try:
            # Try to find our method.
            if self._methods.has_key(name):
                method = self._methods[name]
            else:
                method = self._default_method
            if method is None:
                return self._no_such_method(name)

            # Call our method and return the result.
            return apply(method, params)
       #except:                     # DEBUG
       #    import traceback        #
       #    traceback.print_exc()   #
       #    raise                   #
        except xmlrpclib.Fault, f:
            if f.faultCode == TYPE_ERROR:
                raise TypeError(f.faultString)
            elif f.faultCode == INDEX_ERROR:
                raise IndexError(f.faultString)
            elif f.faultCode == NO_SUCH_METHOD_ERROR:
                raise AttributeError(f.faultString)
            elif f.faultCode == INVALID_UTF8_ERROR:
                raise UnicodeError(f.faultString)
            else:
                raise RuntimeError(f.faultString)
    _dispatch = dispatch_call

    def _no_such_method (self, name):
        """Raise a no-such-method error."""
        raise xmlrpclib.Fault(NO_SUCH_METHOD_ERROR,
                              "Method '%s' not found" % (name))

    def _introspection_check (self):
        """Raise an error if introspection is disabled."""
        if not self._allow_introspection:
            raise xmlrpclib.Fault(INTROSPECTION_DISABLED_ERROR,
                                  ("Introspection has been disabled on this " +
                                   "server, probably for security reasons."))
    
    def system_listMethods (self):
        """Return an array of all available XML-RPC methods on this server.
        """
        self._introspection_check()
        return self._methods.keys()

    def system_methodSignature (self, name):
        """Given the name of a method, return an array of legal signatures. Each
        signature is an array of strings. The first item of each signature is
        the return type, and any others items are parameter types.
        """
        self._introspection_check()
        if self._signatures.has_key(name):
            return self._signatures[name]
        else:
            self._no_such_method(name)

    def system_methodHelp (self, name):
        """Given the name of a method, return a help string.
        """
        self._introspection_check()
        if self._help.has_key(name):
            return self._help[name]
        else:
            self._no_such_method(name)

    def system_multicall (self, calls):
        """Process an array of calls, and return an array of results. Calls
        should be structs of the form {'methodName': string, 'params': array}.
        Each result will either be a single-item array containg the result
        value, or a struct of the form {'faultCode': int, 'faultString':
        string}. This is useful when you need to make lots of small calls
        without lots of round trips.
        """ 
        results = []
        for call in calls:
            try:
                name = call['methodName']
                params = call['params']
                if name == 'system.multicall':
                    errmsg = "Recursive system.multicall forbidden"
                    raise xmlrpclib.Fault(REQUEST_REFUSED_ERROR, errmsg)
                result = [self.dispatch_call(name, params)]
            except xmlrpclib.Fault, fault:
                result = {'faultCode': fault.faultCode,
                          'faultString': fault.faultString}
            except:
                errmsg = "%s:%s" % (sys.exc_type, sys.exc_value)
                result = {'faultCode': 1, 'faultString': errmsg}
            results.append(result)
        return results

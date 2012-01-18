# moosic/client/factory.py - Factory functions for creating Moosic server proxies.
#
# This is free and unencumbered software released into the public domain.
# 
# Anyone is free to copy, modify, publish, use, compile, sell, or
# distribute this software, either in source code form or as a compiled
# binary, for any purpose, commercial or non-commercial, and by any
# means.
# 
# In jurisdictions that recognize copyright laws, the author or authors
# of this software dedicate any and all copyright interest in the
# software to the public domain. We make this dedication for the benefit
# of the public at large and to the detriment of our heirs and
# successors. We intend this dedication to be an overt act of
# relinquishment in perpetuity of all present and future rights to this
# software under copyright law.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
# 
# For more information, please refer to <http://unlicense.org/>

"""Factory functions for creating Moosic server proxies.

This module contains functions that make it very quick and easy to create a
proxy object that exposes all the methods of a Moosic server.  These proxy
objects are instances of xmlrpclib.ServerProxy, so you should refer to the
documentation for the xmlrpclib module for more detailed information about
ServerProxy objects.  These factory functions are not necessary for creating
proper Moosic server proxies, but they are a very convenient way of doing so.

This module also contains a subclass of xmlrpclib.Transport that adapts the
XML-RPC client implementation for use with Unix sockets.

It is safe to "import *" from this module.
"""

import xmlrpclib, urllib, httplib, socket, os, os.path, sys
import moosic.server.main

# Define the True and False constants if they don't already exist.
try: True
except NameError: True = 1
try: False
except NameError: False = 0


__all__ = ('startServer', 'LocalMoosicProxy', 'UnixMoosicProxy',
           'InetMoosicProxy', 'UnixStreamTransport')


class UnixStreamTransport(xmlrpclib.Transport):
    '''An adapter for speaking HTTP over a Unix socket instead of a TCP/IP socket.

    This class mainly exists to serve as a helper for implementing the
    LocalMoosicProxy class, and will not be directly useful for most Moosic
    client developers.
    '''
    def make_connection(self, host):
        class HTTPConnection(httplib.HTTPConnection):
            def connect(self):
                host = urllib.unquote(self.host)
                try:
                    self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    if self.debuglevel > 0:
                        print "connect: (%s)" % host
                    self.sock.connect(host)
                except socket.error, msg:
                    if self.debuglevel > 0:
                        print 'connect fail:', host
                    if self.sock:
                        self.sock.close()
                    self.sock = None
                    raise
        class HTTP(httplib.HTTP):
            _connection_class = HTTPConnection
        # Older versions of xmlrpclib.Transport use the deprecated httplib.HTTP
        # class, while newer versions use httplib.HTTPConnection.
        if sys.version_info < (2,7):
            return HTTP(host)
        else:
            return HTTPConnection(host)


def LocalMoosicProxy(filename=None):
    '''Creates a proxy to a Moosic server that is listening to a local (Unix
    address family) socket.
    
    The optional "filename" argument is the location of the socket file that the
    Moosic server is using as its address.
    '''

    if not filename:
        filename = os.path.join(os.getenv('HOME', '/tmp'), '.moosic', 'socket')
    server_address = 'http://%s/' % urllib.quote(filename, safe='')
    return xmlrpclib.ServerProxy(uri=server_address,
                                 transport=UnixStreamTransport(),
                                 verbose=False)


def UnixMoosicProxy(filename=None):
    '''An alias for the LocalMoosicProxy function.
    '''
    return LocalMoosicProxy(filename)


def InetMoosicProxy(host, port):
    '''Creates a proxy to a Moosic server that is listening to a TCP/IP socket.
    
    The first argument, "host", is the hostname or IP address where the server
    is located. The second argument, "port", is the TCP port that the server is
    listening to.
    '''
    return xmlrpclib.ServerProxy(uri='http://%s:%d/' % (host, port),
                                 verbose=False)


def startServer(*argv):
    '''Attempts to start an instance of the Moosic server.
    
    The parameters given to this function are used verbatim to form the argument
    vector that will be passed to the server process (i.e. sys.argv).  See the
    moosicd(1) man page for a description of valid arguments.
    
    If the server can't be started, a string describing why is returned.
    Otherwise, None is returned.
    '''
    status = None
    try:
        moosic.server.main.main(argv)
    except SystemExit, e:
        status = e[0]
        if not status:
            status = None
        elif type(status) == int:
            status = "The server exited with an exit status of %d." % status
        else:
            status = str(status)
    return status


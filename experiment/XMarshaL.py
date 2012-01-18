#!/usr/bin/env python
# XMarshaL - a pickle/marshal module using xml
# Author:  Joerg Raedler / dezentral - joerg@dezentral.de
# XMarshaL is based on xml.marshal.generic (part of PyXML)
# All rights reserved.
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
# * Redistributions of source code must retain the above copyright
#   notice, this list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above
#   copyright notice, this list of conditions and the following disclaimer
#   in the documentation and/or other materials provided with the distribution.
# * Neither the name of the dezentral gbr nor the names of
#   its contributors may be used to endorse or promote products derived
#   from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""
XMarshaL is a xml marshaller based on xml.marshal.generic,
but with a much better and cleaner interface (IMO).
In some cases, it's magnitudes faster than xml.marshal.generic.
"""
_cvsId = '$Id: XMarshaL.py,v 1.7 2003/08/07 09:40:31 joerg Exp $'
_version = "0.46-bool"
# Modified from the standard version 0.46 by Daniel Pearson <daniel@nanoo.org>
# to add support for the boolean values.

import string, sys, marshal
from types import *
from xml.sax import saxlib, saxexts
try:
    import array
except:
    array = None
try:
    import Numeric
except:
    Numeric = None
try:
    import cPickle as pickle
except:
    import pickle
try:
    import cStringIO as StringIO
except:
    import StringIO


_MARKER  = []

class _EmptyClass:
    pass

class XMarshaLCore(saxlib.HandlerBase):
    """Skeleton of the marshaller class, but without any
    actual code to marshal specific python objects"""
    def __init__(self, *arg, **kwarg):
        self.HEADER = '<?xml version="1.0" encoding="utf-8"?>\n' + \
                      '<!-- created by XMarshaL.py v%s -->\n' % _version
        self.types = {}
        self._clear()

    def dump(self, value, file):
        "Write the value on the open file"
        file.write(self.dumps(value))

    def dumps(self, value):
        "Marshal value, returning the resulting string"
        try:
            r =  "%s%s" % (self.HEADER, self.m_root(value))
        finally:
            self._clear()
        return r

    def _marshal(self, value):
        if self.oDict.has_key(id(value)):
            return self.m_reference(value)
        else:
            m = self.types.get(type(value)) or self.m_unimplemented
            return m(value)

    def register(self, value):
        self.maxId += 1
        self.oDict[id(value)] = self.maxId
        self.oList.append(value)
        return self.maxId

    def _clear(self):
        self.oDict = {}
        self.maxId = 0
        self.oList = []


class XMarshaL(XMarshaLCore):
    """Marshaller which is able to handle a lot of python
    object types"""

    def __init__(self, *arg, **kwarg):
        XMarshaLCore.__init__(self, *arg, **kwarg)
        self.types = {
            NoneType    : self.m_none,
            IntType     : self.m_int,
            LongType    : self.m_long,
            FloatType   : self.m_float,
            StringType  : self.m_string,
            TupleType   : self.m_tuple,
            ListType    : self.m_list,
            DictType    : self.m_dictionary,
            ComplexType : self.m_complex,
            CodeType    : self.m_code,
            InstanceType: self.m_instance,
            ModuleType  : self.m_module}
        if array:
            self.types[array.ArrayType] = self.m_array
        if Numeric:
            self.types[Numeric.ArrayType] = self.m_numeric_array
        try:
            BooleanType # purposefully trigger a NameError in Python < 2.3
            self.types[BooleanType] = self.m_bool
        except NameError:
            pass

    def m_unimplemented(self, value):
        return '<pickle method="pickle" encoding="base64">%s</pickle>' % \
               pickle.dumps(value).encode('base64')

    def m_root(self, value):
        return '<XMarshaL>%s</XMarshaL>' % self._marshal(value)

    def m_reference(self, value):
        return '<reference id="%s"/>' % self.oDict[id(value)]

    def m_string(self, value):
        if '&' in value or '>' in value or '<' in value:
            value = value.replace('&', '&amp;')
            value = value.replace('<', '&lt;')
            value = value.replace('>', '&gt;')
        return '<string>%s</string>' % value.encode('utf-8')

    def m_bool(self, value):
        return '<bool>%s</bool>' % value

    def m_int(self, value):
        return '<int>%s</int>' % value

    def m_float(self, value):
        return '<float>%s</float>' % value

    def m_long(self, value):
        return '<long>%s</long>' % value

    def m_tuple(self, value):
        L = [self._marshal(e) for e in value]
        L.insert(0, '<tuple>')
        L.append('</tuple>')
        return ''.join(L)

    def m_list(self, value):
        i = self.register(value)
        L = [self._marshal(e) for e in value]
        L.insert(0, '<list id="%s">' % i)
        L.append('</list>')
        return ''.join(L)

    def m_array(self, value):
        """array.aray objects - usually large,
        we store an encoded memory buffer as string"""
        return '<array id="%s" typecode="%s" encoding="base64">%s</array>' % \
               (self.register(value), value.typecode, value.tostring().encode('base64'))

    def m_numeric_array(self, value):
        """Numeric.aray objects - usually large,
        we store an encoded memory buffer as string"""
        return '<numeric_array id="%s" encoding="base64">%s</numeric_array>' % \
               (self.register(value), Numeric.dumps(value).encode('base64'))

    def m_dictionary(self, value):
        i =  self.register(value)
        L = ["%s%s" % (self._marshal(k), self._marshal(value[k])) for k in value]
        L.insert(0, '<dictionary id="%s">' % i)
        L.append('</dictionary>')
        return ''.join(L)

    def m_none(self, value):
        return '<none/>'

    def m_complex(self, value):
        return '<complex>%s %s</complex>' % (value.real, value.imag)

    def m_code(self, value):
        return '<code encoding="base64">%s</code>' % \
               marshal.dumps(code).encode('base64')

    def m_module(self, value):
        return '<module>%s</module>' % value.__name__

    def m_instance(self, value):
        if hasattr(value, '__getinitargs__'):
            args = value.__getinitargs__()
        else:
            args = ()
        try:
            getstate = value.__getstate__
        except AttributeError:
            stuff = value.__dict__
        else:
            stuff = getstate()
        return '<object id="%s" module="%s" class="%s">%s%s</object>' % \
               (self.register(value), value.__class__.__module__,
                value.__class__.__name__, self._marshal(args),
                self._marshal(stuff))


class XunMarshaLCore(saxlib.HandlerBase):

    def __init__(self):
        self.startMethods = {}
        self.endMethods   = {}
        self._clear()

    def start_generic(self):
        self.stack.append([])
        self.accumulating_chars = 1

    def register(self, tag, sm, em):
        self.startMethods[tag] = sm
        self.endMethods[tag] = em

    def _clear(self):
        self.stack = []
        self.dict = {}
        self.accumulating_chars = 0
        self.attr = []

    def load(self, file):
        m = self.__class__()
        return m._load(file)

    def loads(self, string):
        m = self.__class__()
        file = StringIO.StringIO(string)
        return m._load(file)

    def _load(self, file):
        p = saxexts.make_parser()
        p.setDocumentHandler(self)
        p.parseFile(file)
        assert len(self.stack) == 1
        result = self.stack[0]
        self._clear()
        return result

    def startElement(self, name, attr):
        self.attr.append(attr)
        m = self.startMethods[name]
        if m: m()

    def characters(self, ch, start, length):
        if self.accumulating_chars:
            self.stack[-1].append(ch[start:start+length])

    def endElement(self, name):
        m = self.endMethods[name]
        if m: m()
        self.accumulating_chars = 0
        del self.attr[-1]


class XunMarshaL(XunMarshaLCore):

    def __init__(self):
        XunMarshaLCore.__init__(self)
        self.register('XMarshaL',   self.start_root,       None)
        self.register('reference',  self.start_reference,  None)
        self.register('int',        self.start_generic,    self.end_int)
        self.register('float',      self.start_generic,    self.end_float)
        self.register('long',       self.start_generic,    self.end_long)
        self.register('string',     self.start_generic,    self.end_string)
        self.register('none',       self.start_generic,    self.end_none)
        self.register('complex',    self.start_generic,    self.end_complex)
        self.register('code',       self.start_generic,    self.end_code)
        self.register('list',       self.start_list,       self.end_list)
        self.register('tuple',      self.start_tuple,      self.end_tuple)
        self.register('dictionary', self.start_dictionary, self.end_dictionary)
        self.register('object',     self.start_instance,   self.end_instance)
        self.register('pickle',     self.start_generic,    self.end_pickle)
        self.register('module',     self.start_generic,    self.end_module)
        self.register('bool',       self.start_generic,    self.end_bool)
        if array:
            self.register('array',  self.start_generic,    self.end_array)
        if Numeric:
            self.register('numeric_array', self.start_generic, self.end_numeric_array)

    def find_class(self, module, name):
        env = {}
        try:
            exec 'from %s import %s' % (module, name) in env
        except ImportError:
            raise SystemError, \
                  "Failed to import class %s from module %s" % \
                  (name, module)
        return env[name]
    
    def start_root(self):
        if self.dict or self.stack:
            raise ValueError, \
                  "root element %s found elsewhere than root" \
                  % repr(name)

    def start_reference(self):
        a = self.attr[-1]
        assert a.has_key('id')
        id = a['id']
        assert self.dict.has_key(id)
        self.stack.append(self.dict[id])

    def end_int(self):
        self.stack[-1] = int(''.join(self.stack[-1]))

    def end_bool(self):
        # Define the True and False constants if they don't already exist.
        try: True
        except NameError: True = 1
        try: False
        except NameError: False = 0
        value = ''.join(self.stack[-1])
        if value == "True":
            self.stack[-1] = True
        elif value == "False":
            self.stack[-1] = False
        else:
            raise ValueError("invalid literal for boolean value: %s" % value)

    def end_long(self):
        self.stack[-1] = long(''.join(self.stack[-1]))

    def end_float(self):
        self.stack[-1] = float(''.join(self.stack[-1]))

    def end_string(self):
        self.stack[-1] = str(''.join(self.stack[-1]))

    def end_none(self):
        self.stack[-1] = None

    def end_complex(self):
        r, i = ''.join(self.stack[-1]).split()
        self.stack[-1] = float(r) + float(i)*1j

    def end_code(self):
        enc = self.attr.get('encoding', 'base64')
        self.stack[-1] = marshal.loads(''.join(self.stack[-1]).decode(enc))

    def end_module(self):
        self.stack[-1] = __import__(str(''.join(self.stack[-1])))

    def start_list(self):
        self.stack.append(_MARKER)
        L = []
        a = self.attr[-1]
        if a.has_key('id'):
            self.dict[a['id']] = L
        self.stack.append(L)

    def end_list(self):
        s = self.stack
        for i in range(len(s)-1, -1, -1):
            if s[i] is _MARKER:
                break
        assert i != -1
        l = s[i+1]
        l[:] = s[i+2:len(s)]
        s[i:] = [l]

    def start_tuple(self):
        self.stack.append(_MARKER)

    def end_tuple(self):
        s = self.stack
        for i in range(len(s) -1, -1, -1):
            if s[i] is _MARKER:
                break
        assert i != -1
        t = tuple(s[i+1:len(s)])
        s[i:] = [t]

    def start_dictionary(self):
        self.stack.append(_MARKER)
        d = {}
        a = self.attr[-1]
        if a.has_key('id'):
            self.dict[a['id']] = d
        self.stack.append(d)

    def end_dictionary(self):
        s = self.stack
        for i in range(len(s) - 1, -1, -1):
            if s[i] is _MARKER:
                break
        assert i != -1
        d = s[i+1]
        for j in range(i+2, len(s), 2):
            d[s[j]] = s[j+1]
        s[i:] = [d]

    def start_instance(self):
        a = self.attr[-1]
        module = a['module']
        classname = a['class']
        value = _EmptyClass()
        if a.has_key('id'):
            self.dict[a['id']] = value
        self.stack.append(value)
        self.stack.append(module)
        self.stack.append(classname)

    def end_instance(self):
        value, module, classname, initargs, dict = self.stack[-5:]
        klass = self.find_class(module, classname)
        if (not initargs and type(klass) is ClassType and
            not hasattr(klass, "__getinitargs__")):
            value.__class__ = klass
        else:
            try:
                v2 = apply(klass, initargs)
            except TypeError, err:
                raise TypeError, "in constructor for %s: %s" % (
                    klass.__name__, str(err)), sys.exc_info()[2]
            else:
                for k,v in v2.__dict__.items():
                    setattr(value, k, v)
        try:
            klass.__setstate__(value, dict)
        except AttributeError:
            value.__dict__.update(dict)
        self.stack[-5:] = [value]

    def end_array(self):
        enc = self.attr[-1]['encoding']
        a = array.array(str(self.attr[-1]['typecode']))
        a.fromstring(str(''.join(self.stack[-1])).decode(enc))
        self.stack[-1] = a

    def end_numeric_array(self):
        enc = self.attr[-1]['encoding']
        a = Numeric.loads(str(''.join(self.stack[-1])).decode(enc))
        self.stack[-1] = a

    def end_pickle(self):
        enc = self.attr[-1]['encoding']
        self.stack[-1] = pickle.loads(str(''.join(self.stack[-1])).decode(enc))

_m = XMarshaL()
dump = _m.dump
dumps = _m.dumps
_um = XunMarshaL()
load = _um.load
loads = _um.loads
del _m, _um

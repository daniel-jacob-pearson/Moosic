# -*- coding: iso-8859-1 -*-
# utilities.py - A library of commonly useful functions and classes.
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

"""A library of commonly useful functions and classes.

This module contains a varied collection of functions and classes that are
potentially useful in a wide range of programming tasks.

It is safe to "import *" from this module.
"""

from __future__ import generators
import re, random, string, operator, os, os.path


__all__ = ('grep', 'antigrep', 'staggered_merge', 'parse_range', 'wrap',
           'xmlrpc_server_doc', 'center_text', 'uniq', 'sh_escape', 'flatten',
           'canLoopOver', 'isStringLike', 'isScalar', 'make_string_filter')


def uniq(seq):
    """Returns a list of all the elements of the given sequence in their
    original order, but without duplicates.
    
    Unlike the Unix tool of the same name, duplicates are removed even if they
    aren't adjacent.  This function only works if the elements of the input
    sequence are hashable.
    """
    d = {}
    return [d.setdefault(i, i) for i in seq if i not in d]


# The following four functions were written by Luther Blissett, and were taken
# from recipe 1.12 in the Python Cookbook.
def canLoopOver(maybeIterable):
    'Tests whether an object can be looped over.'
    try: iter(maybeIterable)
    except: return False
    else: return True


def isStringLike(obj):
    'Tests whether an object behaves like a string.'
    try: obj+''
    except TypeError: return False
    else: return True


def isScalar(obj):
    'Tests whether an object is a scalar value.  Strings are considered scalar.'
    return isStringLike(obj) or not canLoopOver(obj)


def flatten(seq, scalarp=isScalar):
    '''Flattens a nested sequence.
    
    For example, [[1, 2], [3, [4, 5]] becomes [1, 2, 3, 4, 5].
    '''
    for item in seq:
        if scalarp(item):
            yield item
        else:
            for subitem in flatten(item, scalarp):
                yield subitem


def shuffle(seq):
    """Returns a shuffled version of the given sequence. (Deprecated)
 
    The returned list contains exactly the same elements as the given sequence,
    but in a random order.  This function is much slower than the shuffle
    function in the random module in the standard library, and it returns a new
    list instead of shuffling the sequence in place.  Using this function is not
    recommended.
    """
    shuffled = []
    seq = list(seq)
    while seq:
        shuffled.append( seq.pop( random.choice( range( len(seq) ) ) ) )
    return shuffled


def staggered_merge_old(*sequences):
    """Merges multiple sequences, interleaving their elements. (Old version.)
    
    This returns a sequence whose elements alternate between the elements of
    the input sequences.  For example, if the input sequences are (1, 2, 3) and
    (11, 12, 13), then the output will be (1, 11, 2, 12, 3, 13).  And if the
    input sequences are (a, b, c), (v, w, x, y, z), and (q, r, s, t), then the
    output will be (a, v, q, b, w, r, c, x, s, y, t, z).
    
    Beware that this function throws away input elements that are equal to
    None.  This is the price that must be paid in order to merge sequences of
    different lengths.
    """
    # If "sequences" is empty, then the later call to map() won't have enough
    # arguments.  In that case, it is replaced with a 1-tuple whose single
    # element is the empty tuple.
    sequences = sequences or ((),)
    # step 3: filter out the "None" values.
    return filter(
        (lambda x: x is not None),
        # step 2: concatenate the tuples together.
        reduce(
            operator.concat,
            # step 1: collect the corresponding elements into a list of tuples.
            map(*((None,) + sequences)),
                # The argument list for map() must be built dynamically because
                # map() takes a variable number of arguments, and we want each
                # member of "sequences" to be a separate argument to map().
            ()
        )
    )
    # The astute reader might exclaim here that I could have used the builtin
    # zip() function instead of using map() with the identity function.
    # However, zip() truncates all sequences that are longer than the shortest
    # sequence in the series, meaning that elements can get thrown away, which
    # is not what I want.


def staggered_merge(*sequences):
    """Merges multiple sequences, interleaving their elements.
    
    This returns a sequence whose elements alternate between the elements of
    the input sequences.  For example, if the input sequences are (1, 2, 3) and
    (11, 12, 13), then the output will be (1, 11, 2, 12, 3, 13).  And if the
    input sequences are (a, b, c), (v, w, x, y, z), and (q, r, s, t), then the
    output will be (a, v, q, b, w, r, c, x, s, y, t, z).
    
    Backward compatibility notes: This function does not throw away None values
    found in the input sequences, although previous versions did. Also, this
    function always returns a list, while previous versions tended to always
    return a tuple.
    """
    if not len(sequences):
        return []  # base case: there's nothing to merge.
    else:
        cars = [i[0]  for i in sequences if i[:1]] # each list's head item
        cdrs = [i[1:] for i in sequences if i[1:]] # each list's tail items
        return cars + staggered_merge(*cdrs)


def grep(regex, seq):
    """Returns a list of the elements of "seq" that match the regular expression
    represented by "regex", which may be a string or a regular expression
    object.
    """
    if isStringLike(regex):
        regex = re.compile(regex)
    search = regex.search
    return [i for i in seq if search(i)]


def antigrep(regex, seq):
    """Returns a list of the elements of "seq" that do not match the regular
    expression represented by "regex", which may be a string or a regular
    expression object.
    """
    if isStringLike(regex):
        regex = re.compile(regex)
    search = regex.search
    return [i for i in seq if not search(i)]


def parse_range(range, start=0, end=0):
    '''Changes a string representing a range into the indices of the range.
    
    This function converts a string with a form similar to that of the Python
    array slice notation into into a pair of ints which represent the starting
    and ending indices of of the slice.
    
    If the string contains a pair of colon-separated integers, a 2-tuple of
    ints with the respective values of those integers will be returned.  If the
    first number in this pair is omitted, then the value of the "start"
    argument is used.  If the second number in this pair is omitted, then the
    value of the "end" argument is used.
    
    If the string contains a single integer, then a pair of ints with the value
    of that integer and its successor, respectively, will be returned.  The
    exception to this rule is when the successor of the single integer is zero,
    in which case the value of the second element of the returned pair will be
    the value of the "end" argument.
    
    The string can optionally be bracketed by single non-digit, non-dash
    characters at the beginning and/or the end.  The character at the beginning
    doesn't have to be the same as the one at the end.  If either of these
    characters exist, they will be stripped away (and ignored) before any of
    the above-mentioned processing is done.
    
    If the string contains anything else, it is considered invalid and a
    ValueError will be thrown.
    '''
    if not range:
        raise ValueError, 'Invalid range: empty string.'
    if not (range[0].isdigit() or range[0] in ('-', ':')):
        range = range[1:]
    if not (range[-1].isdigit() or range[-1] in ('-', ':')):
        range = range[:-1]
    colon_count = string.count(range, ':')
    if colon_count == 1:
        a, b = string.split(range, ':')
        try:
            if a:
                start = int(a)
            if b:
                end = int(b)
        except ValueError:
            raise ValueError, 'Invalid range (non-integer value): "%s".' % range
    elif colon_count == 0:
        try:
            start = int(range)
        except ValueError:
            raise ValueError, 'Invalid range (non-integer value): "%s".' % range
        if (start + 1) != 0:
            end = start + 1
    else:
        raise ValueError, 'Invalid range (wrong number of colons): "%s".' % range
    return start, end


# The following function was written by Mike Brown, and was taken from the
# Python Cookbook. I would like to dearly thank my grandparents, Sari and Larry
# Pearson, for buying me this book for my birthday.
def wrap(text, width=79):
    """A word-wrap function that preserves existing line breaks and most spaces
    in the text. Expects that existing line breaks are posix newlines (\\n).
    """
    return reduce(lambda line, word, width=width: '%s%s%s' %
                     (line,
                      ' \n'[(len(line[line.rfind('\n')+1:])
                            + len(word.split('\n',1)[0]) >= width)],
                      word),
                     text.split(' ')
                 )


# The following function is modeled after recipe 3.7 from the Python Cookbook,
# which was written by JÜrgen Hermann and Nick Perkins.
def make_string_filter(keep):
    '''Return a function that takes a string and returns a partial copy of that
    string consisting only of the characters in 'keep'.
    '''
    allchars = string.maketrans('', '')
    delchars = allchars.translate(allchars, keep)
    def string_filter(s, a=allchars, d=delchars): return s.translate(a, d)
    return string_filter


def center_text(text, line_width=80, pad_char='-'):
    'Returns the given text centered within a line, with padding.'
    if len(text) > line_width:
        text = text[:line_width-4-3] + '...'
    pad_len = (line_width - len(text) - 2) // 2
    extra = pad_char * (len(text) % 2)
    return '%s %s %s' % (pad_char * pad_len, text, pad_char * pad_len + extra)


def sh_escape(text):
    '''Returns a version of the given text that uses backslashes to make it
    safe to pass to a Bourne-type shell if you enclose it in double quotes.
    '''
    return re.sub(r'([$`\"])', r'\\\1', text)


def xmlrpc_server_doc(server_proxy):
    '''Produces documentation for the methods of an XML-RPC server.
    
    This function queries an XML-RPC server via the introspection API, and
    returns a collection of descriptions that document each of the server's
    methods. The returned collection is a dictionary whose keys are the names of
    the methods and whose values are blurbs of text that describe the methods.
    
    This was inspired by the xml-rpc-api2txt Perl script that comes with
    xmlrpc-c.
    '''
    method_docs = {}
    for method in server_proxy.system.listMethods():
        method_docs[method] = ''
        signature = server_proxy.system.methodSignature(method)
        for sig in signature:
            method_docs[method] += '=item %s B<%s> (%s)\n\n' % \
                                   (sig[0], method, ', '.join(sig[1:]))
        help = server_proxy.system.methodHelp(method)
        method_docs[method] += re.sub(r'(?m)^', r'   ', help)
    return method_docs


def splitpath(path):
    '''Splits a Unix pathname into a list of its components.
 
    If the pathname is absolute, the resulting list will have '/' as its first
    element.
    '''
    plist = []
    while path not in ('/', ''):
        path, plist[0:0] = os.path.dirname(path), [os.path.basename(path)]
    if path:
        plist[0:0] = path
    return plist


def is_overlapping(A, B, n):
    '''Tests whether the slices described by two ranges overlap each other.
    
    Arguments "A" and "B": pairs (2-tuples) of integers, each of which
    represents a range within a sequence.  The first of each pair is the index
    of the first item included in the range, and the second of each pair is the
    index of the item that terminates the range (but is not included in the
    range).
    
    Argument "n": an integer that represents the length of the sequence in which
    these ranges will be applied.  This is needed to handle negative range
    indices sensibly.
    
    Returns: True if the ranges overlap, otherwise False.
    '''
    # Handle negative numbers as range indices.
    if A[0] < 0: A[0] = n - A[0]
    if A[1] < 0: A[1] = n - A[1]
    if B[0] < 0: B[0] = n - B[0]
    if B[1] < 0: B[1] = n - B[1]
    # Any one of these tests indicate overlap.
    if A[0] == B[0]: return True
    if A[1] == B[1]: return True
    if A[0] < B[0] < A[1]: return True
    if A[0] < B[1] < A[1]: return True
    if B[0] < A[0] < B[1]: return True
    if B[0] < A[1] < B[1]: return True
    return False

# moosic/client/cli/dispatcher.py - The code for dispatching moosic commands.
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


__all__ = ("dispatcher", "command_categories", "get_command_docs", "check_args")

import base64, fileinput, sys, os, os.path, time, re
import xmlrpclib, random, errno, string

from moosic.utilities import *
from moosic.client.factory import startServer
from moosic import VERSION

# Portability note: the Unix "find" program is required to be present on the
# system. It is almost unthinkable that you could have a Unix system that
# didn't have the "find" command, but you never know.
try:
    import subprocess
    def call_find(dir):
        return subprocess.Popen(['find',dir,'-follow','-type','f','-print'], \
                stdout=subprocess.PIPE).stdout.readlines()
except ImportError:
    def call_find(dir):
        return os.popen('find "%s" -follow -type f -print' % sh_escape(dir)).readlines()

# Define the True and False constants if they don't already exist.
try: True
except NameError: True = 1
try: False
except NameError: False = 0

command_categories = {
    "add":"Adding to the song queue",
    "remove":"Removing from the song queue",
    "rearrange":"Rearranging the song queue",
    "query":"Querying for information",
    "manage":"Player management",
}

# "dispatcher" is a table that maps moosic command names to the functions that
# implement them.  Each value is a function that accepts 3 arguments: (moosic,
# arglist, opts).  The first argument, "moosic", is the Moosic server proxy that
# is used to communicate with a Moosic server.  The second argument, "arglist",
# is a list of the command's arguments.  The third argument, "opts", is a
# dictionary of the options that were set from the program's command-line
# switches.
# 
# Every function in this table must have the following attributes:
#
#  category - One of the keys from the command_categories dictionary.
#  num_args - One of the following: "zero", "zero_or_one", "zero_or_many",
#          "one", "two", "two_or_three", "many".
#  __doc__ - A string that contains a one-line description of the command's
#        behavior.
#
# Note that the return value of each of these functions is interpreted by the
# "moosic" program as an exit status for the program (by feeding the returned
# value to sys.exit()).
dispatcher = {}


#--------------------------- Public Helper Functions --------------------------#

def get_command_docs():
    'Gathers the doc strings for all the moosic commands into a single string.'
    doc = ''
    for category in command_categories:
        doc += center_text(command_categories[category]) + '\n'
        commands = [command for command in dispatcher
                    if dispatcher[command].category == category]
        commands.sort()
        for command in commands:
            doc += dispatcher[command].__doc__.strip() + '\n\n'
    return doc


def check_args(command, arglist):
    '''Checks a list of arguments to see if they are valid for a command.
    
    The first parameter, command, is a string that represents the name of the
    command in question.  The second parameter, args, is the list of arguments
    to be checked.  Returns True if the argument list is valid, otherwise False.
    
    The behavior of this function depends on the value of the num_args attribute
    of the function object associated with the command. num_args should have one
    of the following values: "zero", "zero_or_one", "zero_or_many", "one",
    "two", "two_or_three", "many".
    '''
    err = sys.stderr  # Giving stderr a shorter name is convenient when printing
                      # error messages.
    # Check the number of arguments given to the command.
    if dispatcher[command].num_args not in ("zero", "zero_or_one", "zero_or_many"):
        if not arglist:
            print >>err, \
                'Error: the "%s" command requires at least one argument.' % command
            return False

    if dispatcher[command].num_args == "zero":
        if arglist:
            print >>err, \
                'Warning: the "%s" command doesn\'t take any arguments.' % command
            print >>err, 'The given arguments will be ignored.'

    elif dispatcher[command].num_args == "one":
        if len(arglist) != 1:
            print >>err, \
                'Warning: the "%s" command takes only one argument.' % command
            print >>err, 'Extraneous arguments beyond the first will be ignored.'

    elif dispatcher[command].num_args == "zero_or_one":
        if len(arglist) > 1:
            print >>err, \
                'Warning: the "%s" command takes at most one argument.' % command
            print >>err, 'Extraneous arguments beyond the first will be ignored.'

    elif dispatcher[command].num_args == "two":
        if len(arglist) != 2:
            print >>err, \
                'Error: the "%s" command requires exactly two arguments.' % command
            return False

    elif dispatcher[command].num_args == "two_or_three":
        if len(arglist) > 3:
            print >>err, \
                'Warning: the "%s" command takes at most three arguments.' % command
            print >>err, 'Extraneous arguments beyond the third will be ignored.'
        if len(arglist) < 2:
            print >>err, \
                'Error: the "%s" command requires at least two arguments.' % command
            return False

    # Pluck off the "index" argument to the insert and pl-insert commands
    # before processing the rest of their argument lists.
    if command == 'insert' or command == 'pl-insert':
        try:
            index = arglist.pop()
            if not (index[0].isdigit() or index[0] == '-'):
                index = index[1:]
            if not (index[-1].isdigit() or index[-1] == '-'):
                index = index[:-1]
            dispatcher['insert'].position = int(index)
        except ValueError, e:
            print >>err, "Error:", e
            print >>err, "An integer is required as the final argument."
            return False
        if not arglist:
            print >>err, \
                'Error: the "%s" command needs something to insert.' % command
            return False
    return True


#-------------------------- Private Helper Functions --------------------------#

def unmangle(s):
    '''Certain command names are invalid Python identifiers. This converts a
    command name that was mangled into a valid identifier into its original
    form.  It also lowers the case of the given string for normalization
    purposes.'''
    return re.sub(r'[\W_]', r'', s).lower()


def read_playlists(playlists, opts):
    '''Inputs a list of playlist file-names and outputs a list of the
    file names contained in the playlists.'''
    arglist = []
    for line in fileinput.input(playlists):
        # skip empty lines
        if re.search(r'^\s*$', line):
            continue
        # skip lines that begin with a '#' character
        if re.search(r'^#', line):
            continue
        # chomp off trailing newlines
        if line.endswith('\n'):
            line = line[:-1]
        # tack the dirname onto the front of relative paths
        if not os.path.isabs(line) and opts['file-munge']:
            arglist.append(os.path.join(os.path.dirname(fileinput.filename()), line))
        else:
            arglist.append(line)
    return arglist


def process_filelist(moosic, arglist, opts):
    if opts['auto-grep']:
        # Be case-insensitive if that was requested.
        if opts['ignore-case']:
            arglist = [i + '(?i)' for i in arglist]
        # Get a list of filenames which are eligible for auto-finding.
        files = call_find(opts['music-dir'])
        files.sort()
        # Strip off the trailing EOL character.
        files = [item[:-1] for item in files]
        # Grep the list of filenames for each regex argument, and include each
        # grep result in the output list.
        output = []
        [output.extend(grep(a, files)) for a in arglist]
        arglist = output
    if opts['auto-find']: # This feature was inspired by David McCabe.
        del_non_wordchars = make_string_filter(string.letters+string.digits+'/')
        def simplify(s):
            return del_non_wordchars(s).lower()
        # Simplify the strings to be sought after.
        arglist = [simplify(a) for a in arglist]
        # Get a list of filenames which are eligible for auto-finding.
        files = call_find(opts['music-dir'])
        # Strip off the trailing EOL character.
        files = [item[:-1] for item in files]
        # Simplify the filenames to be searched through, and map each simplified
        # name to the original name.
        names = {}
        [names.setdefault(simplify(f), []).append(f) for f in files]
        # If an argument is a substring of one of the simplified filenames,
        # include the full filename in the output list.
        output = []
        # Using the "in" operator to find substrings doesn't work in Python 2.2 :(
        #[output.extend(names[n]) for a in arglist for n in names if (a and a in n)]
        [output.extend(names[n])
            for a in arglist
                for n in names
                    if (a and n.find(a) != -1)]
        output.sort()
        arglist = output
    # When dealing with local files, all filenames should be specified by
    # their absolute paths before telling the server to play them.  Using
    # relative pathnames would be foolish because the server has no idea
    # what our current working directory is.
    if opts['file-munge']:
        arglist = map(os.path.expanduser, arglist)
        arglist = map(os.path.abspath, arglist)
    if opts['shuffle-args']:
        random.shuffle(arglist)
    # If an item in the filelist is a directory, then recurse through the
    # directory, replacing the item with its children.
    if opts['dir-recurse']:
        pos = 0
        while pos < len(arglist):
            if os.path.isdir(arglist[pos]):
                contents = call_find(arglist.pop(pos))
                # Strip off the trailing EOL character.
                contents = [item[:-1] for item in contents]
                if opts['shuffle-dir']:
                    random.shuffle(contents)
                else:
                    contents.sort()
                    contents.reverse()
                for item in contents:
                    arglist.insert(pos, item)
            pos = pos + 1
    if opts['shuffle-global']:
        random.shuffle(arglist)
    if opts['sort']:
        arglist.sort()
    if opts['no-unplayables']:
        playable_patterns = [entry[0].data for entry in moosic.getconfig()]
        newlist = []
        for i in arglist:
            for pat in playable_patterns:
                if re.search(pat, i):
                    newlist.append(i)
                    break
        arglist = newlist
    return arglist

#---------------------------- Dispatcher functions ----------------------------#

def start_server(moosic, arglist, opts):
    "start-server [server-options] - Start the server when it isn't already running."
    if opts['tcp-address']:
        print >>sys.stderr, \
                wrap("Warning: the Moosic server is being started on the local "
                     "computer, even though you specified the -t option, which "
                     "usually causes this client to interact with a server on "
                     "a remote computer. This is probably not what you want.")
    if not arglist:
        arglist = ['-c', opts['config-dir']]
    return startServer(*(['moosicd'] + arglist))

f = start_server
f.category = 'manage'
f.num_args = 'zero_or_many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def append(moosic, arglist, opts):
    'append <filelist> - Add files to the end of the song queue.'
    arglist = process_filelist(moosic, arglist, opts)
    arglist = [xmlrpclib.Binary(i) for i in arglist]
    moosic.append(arglist)

f = append
f.category = 'add'
f.num_args = 'many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def add(moosic, arglist, opts):
    'add <filelist> - An alias for "append".'
    append(moosic, arglist, opts)

f = add
f.category = 'add'
f.num_args = 'many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def pl_append(moosic, arglist, opts):
    "pl-append <playlists> - Add the playlists' contents to the end of the queue."
    arglist = read_playlists(arglist, opts)
    append(moosic, arglist, opts)

f = pl_append
f.category = 'add'
f.num_args = 'many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def pl_add(moosic, arglist, opts):
    'pl-add <playlists> - An alias for "pl-append".'
    pl_append(moosic, arglist, opts)

f = pl_add
f.category = 'add'
f.num_args = 'many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def prepend(moosic, arglist, opts):
    'prepend <filelist> - Add files to the beginning of the song queue.'
    arglist = process_filelist(moosic, arglist, opts)
    arglist = [xmlrpclib.Binary(i) for i in arglist]
    moosic.prepend(arglist)

f = prepend
f.category = 'add'
f.num_args = 'many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def pre(moosic, arglist, opts):
    'pre <filelist> - An alias for "prepend".'
    prepend(moosic, arglist, opts)

f = pre
f.category = 'add'
f.num_args = 'many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def pl_prepend(moosic, arglist, opts):
    "pl-prepend <playlists> - Add playlists' contents to the start of the queue."
    arglist = read_playlists(arglist, opts)
    prepend(moosic, arglist, opts)

f = pl_prepend
f.category = 'add'
f.num_args = 'many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def mixin(moosic, arglist, opts):
    'mixin <filelist> - Add files to the song queue and reshuffle the entire queue.'
    arglist = process_filelist(moosic, arglist, opts)
    arglist = [xmlrpclib.Binary(i) for i in arglist]
    moosic.append(arglist)
    moosic.shuffle()

f = mixin
f.category = 'add'
f.num_args = 'many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def pl_mixin(moosic, arglist, opts):
    "pl-mixin <playlists> - Add playlists' contents to the queue and reshuffle all."
    arglist = read_playlists(arglist, opts)
    mixin(moosic, arglist, opts)

f = pl_mixin
f.category = 'add'
f.num_args = 'many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def putback(moosic, arglist, opts):
    'putback - Reinsert the current song at the start of the song queue.'
    moosic.putback()

f = putback
f.category = 'add'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def insert(moosic, arglist, opts):
    'insert <filelist> <index> - Insert files at a specific point in the song queue.'
    arglist = process_filelist(moosic, arglist, opts)
    arglist = [xmlrpclib.Binary(i) for i in arglist]
    moosic.insert(arglist, insert.position)

insert.position = 0
f = insert
f.category = 'add'
f.num_args = 'many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def pl_insert(moosic, arglist, opts):
    """pl-insert <playlists> <index> - Insert playlists' contents at a specific point
    the song queue."""
    arglist = read_playlists(arglist, opts)
    insert(moosic, arglist, opts)

f = pl_insert
f.category = 'add'
f.num_args = 'many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def replace(moosic, arglist, opts):
    "replace <filelist> - Clear the current the queue and add a new list of songs."
    arglist = process_filelist(moosic, arglist, opts)
    arglist = [xmlrpclib.Binary(i) for i in arglist]
    moosic.replace(arglist)

f = replace
f.category = 'add'
f.num_args = 'many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def pl_replace(moosic, arglist, opts):
    """pl-replace <playlists> - Clear the current the queue and add new songs from
    playlists."""
    arglist = read_playlists(arglist, opts)
    replace(moosic, arglist, opts)

f = pl_replace
f.category = 'add'
f.num_args = 'many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def interval_add(moosic, arglist, opts):
    '''interval-add <interval> <filelist> - Insert songs into the current queue
    at the specified interval.'''
    try:
        interval = int(arglist[0])
    except ValueError, e:
        print >>err, "Error:", e
        print >>err, "An integer is required as the first argument."
        return 2
    new_songs = process_filelist(moosic, arglist[1:], opts)
    for i in range(len(new_songs)):
        moosic.insert([xmlrpclib.Binary(new_songs[i])], i*interval)

f = interval_add
f.category = 'add'
f.num_args = 'many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def cut(moosic, arglist, opts):
    'cut <range> - Remove all queued items that fall within the given range.'
    start, end = parse_range(arglist[0], 0, None)
    if end is None:
        moosic.cut((start,))
    else:
        moosic.cut((start, end))

f = cut
f.category = 'remove'
f.num_args = 'one'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def del_(moosic, arglist, opts):
    'del <range> - An alias for "cut".'
    cut(moosic, arglist, opts)

f = del_
f.category = 'remove'
f.num_args = 'one'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def crop(moosic, arglist, opts):
    'crop <range> - Remove all queued items that do NOT fall within the given range.'
    start, end = parse_range(arglist[0], 0, None)
    if end is None:
        moosic.crop((start,))
    else:
        moosic.crop((start, end))

f = crop
f.category = 'remove'
f.num_args = 'one'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def remove(moosic, arglist, opts):
    'remove <regex-list> - Remove all queued items that match the given regex(s).'
    if opts['ignore-case']:
        arglist = [i + '(?i)' for i in arglist]
    arglist = [xmlrpclib.Binary(i) for i in arglist]
    for pattern in arglist:
        moosic.remove(pattern)

f = remove
f.category = 'remove'
f.num_args = 'many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def filter_(moosic, arglist, opts):
    'filter <regex-list> - Remove all queued items that do NOT match the given regex.'
    if opts['ignore-case']:
        arglist = [i + '(?i)' for i in arglist]
    arglist = [xmlrpclib.Binary(i) for i in arglist]
    for pattern in arglist:
        moosic.filter(pattern)

f = filter_
f.category = 'remove'
f.num_args = 'many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def clear(moosic, arglist, opts):
    'clear - Clear the song queue.'
    moosic.clear()

f = clear
f.category = 'remove'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def wipe(moosic, arglist, opts):
    'wipe - Clear the song queue and stop the current song.'
    was_running = False
    if moosic.is_queue_running():
        moosic.halt_queue()
        was_running = True
    moosic.stop()
    moosic.clear()
    if was_running:
        moosic.run_queue()

f = wipe
f.category = 'remove'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def move(moosic, arglist, opts):
    '''move <range> <index> - Moves all items in the given range to a new position in
    the song queue.'''
    start, end = parse_range(arglist[0], 0, None)
    dest = arglist[1]
    if not (dest[0].isdigit() or dest[0] == '-'):
        dest = dest[1:]
    if not (dest[-1].isdigit() or dest[-1] == '-'):
        dest = dest[:-1]
    dest = int(dest)
    if end is None:
        moosic.move((start,), dest)
    else:
        moosic.move((start, end), dest)

f = move
f.category = 'rearrange'
f.num_args = 'two'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def move_pattern(moosic, arglist, opts):
    '''move-pattern <regex> <index> - Moves all items that match the given regex
    to a new position in the song queue.'''
    pattern, destination = arglist
    try:
        if not (destination[0].isdigit() or destination[0] == '-'):
            destination = destination[1:]
        if not (destination[-1].isdigit() or destination[-1] == '-'):
            destination = destination[:-1]
        destination = int(destination)
    except ValueError, e:
        print >>err, 'Error:', e 
        print >>err, 'An integer is required as the final argument.'
        return 2
    all_items = [i.data for i in moosic.list()]
    if opts['ignore-case']:
        pattern += '(?i)'
    items_to_move = grep(pattern, all_items)
    head = antigrep(pattern, all_items[:destination])
    tail = antigrep(pattern, all_items[destination:])
    all_items = head + items_to_move + tail
    moosic.replace([xmlrpclib.Binary(i) for i in all_items])

f = move_pattern
f.category = 'rearrange'
f.num_args = 'two'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def swap(moosic, arglist, opts):
    '''swap <range> <range> - Causes two segments of the queue to trade places.'''
    r1 = parse_range(arglist[0], 0, None)
    r2 = parse_range(arglist[1], 0, None)
    if r1[1] is None:
        r1 = (r1[0],)
    if r2[1] is None:
        r2 = (r2[0],)
    moosic.swap(r1, r2)

f = swap
f.category = 'rearrange'
f.num_args = 'two'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def shuffle_(moosic, arglist, opts):
    'shuffle [range] - Put contents of the song queue into a random order.'
    if arglist:
        start, end = parse_range(arglist[0], 0, None)
    else:
        start, end = 0, None
    if end is None:
        moosic.shuffle((start,))
    else:
        moosic.shuffle((start, end))

f = shuffle_
f.category = 'rearrange'
f.num_args = 'zero_or_one'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def reshuffle(moosic, arglist, opts):
    'reshuffle [range] - An alias for "shuffle".'
    shuffle_(moosic, arglist, opts)

f = reshuffle
f.category = 'rearrange'
f.num_args = 'zero_or_one'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def sort(moosic, arglist, opts):
    'sort [range] - Rearrange the song queue in sorted order.'
    if arglist:
        start, end = parse_range(arglist[0], 0, None)
    else:
        start, end = 0, None
    if end is None:
        moosic.sort((start,))
    else:
        moosic.sort((start, end))

f = sort
f.category = 'rearrange'
f.num_args = 'zero_or_one'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def reverse(moosic, arglist, opts):
    'reverse [range] - Reverse the order of the song queue.'
    if arglist:
        start, end = parse_range(arglist[0], 0, None)
    else:
        start, end = 0, None
    if end is None:
        moosic.reverse((start,))
    else:
        moosic.reverse((start, end))

f = reverse
f.category = 'rearrange'
f.num_args = 'zero_or_one'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def partial_sort(moosic, arglist, opts):
    'partial-sort <regex-list> - Separate the queue items into categories.'
    items = [i.data for i in moosic.list()]
    buckets = {}
    if opts['ignore-case']:
        arglist = [i + '(?i)' for i in arglist]
    for pattern in arglist:
        # Store all items that match the pattern.
        buckets[pattern] = grep(pattern, items)
        # Only do further processing on the items that were not matched.
        items = antigrep(pattern, items)
    leftovers = items
    items = []
    [items.extend(buckets[pattern]) for pattern in arglist]
    items.extend(leftovers)
    items = [xmlrpclib.Binary(i) for i in items]
    moosic.replace(items)

f = partial_sort
f.category = 'rearrange'
f.num_args = 'many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def stagger(moosic, arglist, opts):
    '''stagger <regex-list> - Arrange the queue contents into a list that alternates
    between two or more categories.'''
    items = [i.data for i in moosic.list()]
    list_of_lists = []
    if opts['ignore-case']:
        arglist = [i + '(?i)' for i in arglist]
    for pattern in arglist:
        # Collect all items that match the pattern.
        list_of_lists.append(grep(pattern, items))
        # Only do further processing on the items that were not matched.
        items = antigrep(pattern, items)
    # Perform a staggered merge on all the lists we collected, along
    # with any remaining items.
    items = staggered_merge(*(list_of_lists)) + items
    items = [xmlrpclib.Binary(i) for i in items]
    moosic.replace(items)

f = stagger
f.category = 'rearrange'
f.num_args = 'many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def sub(moosic, arglist, opts):
    '''sub <regex> <replace> [range] - Perform a regular expression substitution
    on the items in the queue.'''
    if len(arglist) > 2:
        start, end = parse_range(arglist[2], 0, None)
    else:
        start, end = 0, None
    if end is None:
        range = (start,)
    else:
        range = (start, end)
    bin = xmlrpclib.Binary
    moosic.sub(bin(arglist[0]), bin(arglist[1]), range)

f = sub
f.category = 'rearrange'
f.num_args = 'two_or_three'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def suball(moosic, arglist, opts):
    '''suball <regex> <replace> [range] - Perform a global regular expression
    substitution on the items in the queue.'''
    if len(arglist) > 2:
        start, end = parse_range(arglist[2], 0, None)
    else:
        start, end = 0, None
    if end is None:
        range = (start,)
    else:
        range = (start, end)
    bin = xmlrpclib.Binary
    moosic.sub_all(bin(arglist[0]), bin(arglist[1]), range)

f = suball
f.category = 'rearrange'
f.num_args = 'two_or_three'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def stagger_add(moosic, arglist, opts):
    '''stagger-add <filelist> - Arrange the given file list into an alternating order
    and then add it to the queue.'''
    items = process_filelist(moosic, arglist, opts)
    list_of_lists = []
    for pattern in [re.escape(pattern) for pattern in arglist]:
        # Collect all items that match the pattern.
        list_of_lists.append(grep(pattern, items))
        # Only do further processing on the items that were not matched.
        items = antigrep(pattern, items)
    # Perform a staggered merge on all the lists we collected, along
    # with any remaining items.
    items = staggered_merge(*(list_of_lists + [items]))
    items = [xmlrpclib.Binary(i) for i in items]
    moosic.append(items)

f = stagger_add
f.category = 'add'
f.num_args = 'many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def stagger_merge(moosic, arglist, opts):
    '''stagger-merge <filelist> - Interleave the given file list into the song queue.
    '''
    new_items = process_filelist(moosic, arglist, opts)
    old_items = [i.data for i in moosic.list()]
    items = [xmlrpclib.Binary(i) for i in staggered_merge(new_items, old_items)]
    moosic.replace(items)

f = stagger_merge
f.category = 'add'
f.num_args = 'many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def current(moosic, arglist, opts):
    'current - Print the name of the song that is currently playing.'
    print moosic.current().data

f = current
f.category = 'query'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def curr(moosic, arglist, opts):
    'curr - An alias for "current".'
    current(moosic, arglist, opts)

f = curr
f.category = 'query'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def current_time(moosic, arglist, opts):
    '''current-time [format] - Print the amount of time that the current song has 
    been playing.'''
    if arglist:
        print time.strftime(arglist[0], time.gmtime(moosic.current_time()))
    else:
        print time.strftime('%H:%M:%S', time.gmtime(moosic.current_time()))
    #current_time = moosic.current_time()
    #hours, remainder = divmod(current_time, 3600)
    #minutes, seconds = divmod(remainder, 60)
    #print '%d:%02d:%02d' % (hours, minutes, seconds)

f = current_time
f.category = 'query'
f.num_args = 'zero_or_one'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def list_(moosic, arglist, opts):
    '''list [range] - Print the list of items in the current song queue. If a range is
    specified, only the items that fall within that range are listed.'''
    if arglist:
        start, end = parse_range(arglist[0], 0, None)
    else:
        start, end = 0, None
    if opts['current-in-list']:
        if arglist:
            print >>sys.stderr, wrap("Warning: the -C option has no effect "
                    "if an argument is given.")
        else:
            print "[*]", moosic.current().data
    if end is None:
        d = moosic.indexed_list((start,))
    else:
        d = moosic.indexed_list((start, end))
    index, items = d['start'], d['list']
    for item in items:
        try:
            print '[%d] %s' % (index, item.data)
            index += 1
        except IOError, e:
            if e[0] == errno.EPIPE:
                break # Ignore "broken pipe" errors.
            else:
                raise e

f = list_
f.category = 'query'
f.num_args = 'zero_or_one'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def plainlist(moosic, arglist, opts):
    'plainlist [range] - Print the current song queue without numbering each line.'
    if arglist:
        start, end = parse_range(arglist[0], 0, None)
    else:
        start, end = 0, None
    try:
        if opts['current-in-list']:
            if arglist:
                print >>sys.stderr, wrap("Warning: the -C option has no effect "
                        "if an argument is given.")
            else:
                print moosic.current().data
        if end is None:
            print '\n'.join([i.data for i in moosic.list((start,))])
        else:
            print '\n'.join([i.data for i in moosic.list((start, end))])
    except IOError, e:
        if e[0] == errno.EPIPE:
            # Ignore "broken pipe" errors.
            pass
        else:
            raise e

f = plainlist
f.category = 'query'
f.num_args = 'zero_or_one'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def history(moosic, arglist, opts):
    'history [number] - Print a list of files that were recently played.'
    if not arglist:
        num = 0
    else:
        try: num = int(arglist[0])
        except ValueError, e:
            print "Error:", e
            print 'The argument to the "history" command must be an integer.'
            sys.exit(1)
    for item, starttime, endtime in moosic.history(num):
        item = item.data
        endtime = time.strftime('%I:%M:%S%p', time.localtime(endtime))
        print string.join((endtime, item))

f = history
f.category = 'query'
f.num_args = 'zero_or_one'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def hist(moosic, arglist, opts):
    'hist [number] - An alias for "history".'
    history(moosic, arglist, opts)

f = hist
f.category = 'query'
f.num_args = 'zero_or_one'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def state(moosic, arglist, opts):
    'state - Print the current state of the music daemon.'
    current_song = moosic.current().data
    if current_song != '':
        print 'Currently playing: "%s"' % current_song
    else:
        print 'Nothing is currently playing.'
    if moosic.is_paused():
        print 'The current song is paused.'
    else:
        print 'The current song is not paused.'
    if moosic.is_queue_running():
        print 'Queue advancement is enabled.'
    else:
        print 'Queue advancement is disabled.'
    if moosic.is_looping():
        print 'Loop mode is on.'
    else:
        print 'Loop mode is off.'
    print "There are %d items in the queue." % moosic.queue_length()

f = state
f.category = 'query'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def status(moosic, arglist, opts):
    'status - An alias for "state".'
    state(moosic, arglist, opts)

f = status
f.category = 'query'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def length(moosic, arglist, opts):
    'length - Print the number of items in the queue.'
    print moosic.queue_length()

f = length
f.category = 'query'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def len_(moosic, arglist, opts):
    'len - An alias for "length".'
    length(moosic, arglist, opts)

f = len_
f.category = 'query'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def ispaused(moosic, arglist, opts):
    'ispaused - Show whether the current song is paused.'
    if moosic.is_paused():
        print "True"
        return 0
    else:
        print "False"
        return 1

f = ispaused
f.category = 'query'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def islooping(moosic, arglist, opts):
    'islooping - Show whether the server is in loop mode.'
    if moosic.is_looping():
        print "True"
        return 0
    else:
        print "False"
        return 1

f = islooping
f.category = 'query'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def isadvancing(moosic, arglist, opts):
    'isadvancing - Show whether the server is advancing through the song queue.'
    if moosic.is_queue_running():
        print "True"
        return 0
    else:
        print "False"
        return 1

f = isadvancing
f.category = 'query'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def version(moosic, arglist, opts):
    'version - Print version information for the client and server, and then exit.'
    print 'Moosic Client version:', VERSION
    print 'Moosic Server version:', moosic.version()

f = version
f.category = 'query'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def next(moosic, arglist, opts):
    'next [number] - Skip ahead in the song queue.'
    if arglist:
        try:
            howmany = int(arglist[0])
        except ValueError, e:
            print "Error:", e
            print 'The argument to the "next" command must be an integer.'
            sys.exit(1)
        moosic.next(howmany)
    else:
        moosic.next()

f = next
f.category = 'manage'
f.num_args = 'zero_or_one'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def previous(moosic, arglist, opts):
    '''previous [number] - Returns the most recently played song(s) to the queue
    and starts playing.'''
    if arglist:
        try:
            howmany = int(arglist[0])
        except ValueError, e:
            print "Error:", e
            print 'The argument to the "previous" command must be an integer.'
            sys.exit(1)
        moosic.previous(howmany)
    else:
        moosic.previous()

f = previous
f.category = 'manage'
f.num_args = 'zero_or_one'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def prev(moosic, arglist, opts):
    'prev - An alias for "previous".'
    previous(moosic, arglist, opts)

f = prev
f.category = 'manage'
f.num_args = 'zero_or_one'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def goto(moosic, arglist, opts):
    'goto <regex> - Jump to the first song in the queue that matches the regex.'
    if opts['ignore-case']:
        arglist = [i + '(?i)' for i in arglist]
    queue = moosic.list()
    dest = 1
    while queue:
        if re.search(arglist[0], queue[0].data):
            break
        dest += 1
        queue.pop(0)
    if queue:
        if not moosic.current().data:
            dest -= 1
        moosic.next(dest)
    else:
        print 'No match found:', arglist[0]

f = goto
f.category = 'manage'
f.num_args = 'one'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def gobackto(moosic, arglist, opts):
    'gobackto <regex> - Jump to the previous song that matches the regex.'
    if opts['ignore-case']:
        arglist = [i + '(?i)' for i in arglist]
    history = moosic.history()
    dest = 1
    while history:
        if re.search(arglist[0], history[-1][0].data):
            break
        dest += 1
        history.pop()
    if history:
        moosic.previous(dest)
    else:
        print 'No match found:', arglist[0]

f = gobackto
f.category = 'manage'
f.num_args = 'one'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def noadvance(moosic, arglist, opts):
    'no-advance - Stop playing any new songs, but without interrupting the current song.'
    moosic.halt_queue()

f = noadvance
f.category = 'manage'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def noadv(moosic, arglist, opts):
    'no-adv - An alias for "noadvance".'
    noadvance(moosic, arglist, opts)

f = noadv
f.category = 'manage'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def advance(moosic, arglist, opts):
    'advance - Activate advancement through the song queue.'
    moosic.run_queue()

f = advance
f.category = 'manage'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def adv(moosic, arglist, opts):
    'adv - An alias for "advance".'
    advance(moosic, arglist, opts)

f = adv
f.category = 'manage'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def toggle_advance(moosic, arglist, opts):
    '''toggle-advance - Halts queue advancement if it is enabled, and enables
    advancement if it is halted.'''
    if moosic.is_queue_running():
        moosic.halt_queue()
    else:
        moosic.run_queue()

f = toggle_advance
f.category = 'manage'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def stop(moosic, arglist, opts):
    '''stop - Stop playing the current song and stop playing new songs. The
    current song is put back into the song queue as if it had not been played.'''
    moosic.stop()

f = stop
f.category = 'manage'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

# FIXME: this needs a good name
def stop_but_no_replay(moosic, arglist, opts):
    '''stop_but_no_replay - Stop playing the current song and stop processing
    the song queue.'''
    moosic.halt_queue()
    moosic.skip()

f = stop_but_no_replay
f.category = 'manage'
f.num_args = 'zero'
#dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def pause(moosic, arglist, opts):
    '''pause - Suspend the current song so that it can be resumed at the exact same
    point at a later time. Note: this often leaves the sound device locked.'''
    moosic.pause()

f = pause
f.category = 'manage'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def unpause(moosic, arglist, opts):
    '''unpause - Unpause the current song if the current song is paused, otherwise do
    nothing.'''
    moosic.unpause()

f = unpause
f.category = 'manage'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def toggle_pause(moosic, arglist, opts):
    '''toggle-pause - Pause the current song if it is not already paused, and unpause
    the current song if it is already paused.'''
    moosic.toggle_pause()

f = toggle_pause
f.category = 'manage'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def play(moosic, arglist, opts):
    'play - Resume playing. (Use after "stop", "sleep", "noplay", or "pause".)'
    moosic.run_queue()
    moosic.unpause()

f = play
f.category = 'manage'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def loop(moosic, arglist, opts):
    'loop - Turn loop mode on.'
    moosic.set_loop_mode(True)

f = loop
f.category = 'manage'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def noloop(moosic, arglist, opts):
    'noloop - Turn loop mode off.'
    moosic.set_loop_mode(False)

f = noloop
f.category = 'manage'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def toggle_loop(moosic, arglist, opts):
    'toggle-loop - Turn loop mode on if it is off, and turn it off if it is on.'
    moosic.toggle_loop_mode()

f = toggle_loop
f.category = 'manage'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def reconfigure(moosic, arglist, opts):
    'reconfigure - Reload the player configuration file.'
    moosic.reconfigure()

f = reconfigure
f.category = 'manage'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def reconfig(moosic, arglist, opts):
    'reconfig - An alias for "reconfigure".'
    reconfigure(moosic, arglist, opts)

f = reconfig
f.category = 'manage'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def showconfig(moosic, arglist, opts):
    'showconfig - Query and print the filetype to song player associations.'
    print moosic.showconfig().data

f = showconfig
f.category = 'manage'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def help(moosic, arglist, opts):
    'help [commands] - Get documentation on the available moosic commands.'
    if not arglist:
        print 'The following commands are available:'
        col_count = 0
        commands = dispatcher.keys()
        commands.sort()
        for command in commands:
            if dispatcher[command].category not in command_categories:
                continue
            print command,
            col_count += 1
            if not col_count % 5:
                print
            else:
                print ' ' * (13 - len(command)),
        if col_count % 5:
            print
        print 'Use "' + os.path.basename(sys.argv[0]),
        print 'help <command>" to display help for a particular command.'
    else:
        for command in arglist:
            command = unmangle(command.lower())
            if command in dispatcher:
                print dispatcher[command].__doc__
            else:
                print "No such command:", command

f = help
f.category = 'query'
f.num_args = 'zero_or_many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def exit(moosic, arglist, opts):
    'exit - Tell the music daemon to quit.'
    moosic.die()

f = exit
f.category = 'manage'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def quit(moosic, arglist, opts):
    'quit - An alias for "exit".'
    exit(moosic, arglist, opts)

f = quit
f.category = 'manage'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def die(moosic, arglist, opts):
    'die - An alias for "exit".'
    exit(moosic, arglist, opts)

f = die
f.category = 'manage'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def moo(moosic, arglist, opts):
    print base64.decodestring('''\
ICAgICAgICAoX19fKSAgIChfX18pICAoX19fKSAoX19fKSAgICAgIChfX18pICAgKF9fXykgICAo
X19fKSAoX19fKSAgICAgCiAgICAgICAgKG8gbyhfX18pbyBvKShfX18pbykgKG8gbykgKF9fXyko
byBvKF9fXylvIG8pKF9fXykgbykgKG8gbykoX19fKQogICAgICAgICBcIC8obyBvKVwgLyAobyBv
KS8gKF9fXykgIChvIG8pIFwgLyhvIG8pXCAvIChvIG8pIC8oX19fKS8gKG8gbykKICAgICAgICAg
IE8gIFwgLyAgTyAgIFwgL08gIChvIG8pICAgXCAvICAgTyAgXCAvICBPICAgXCAvIE8gKG8gbykg
ICBcIC8gCiAgICAgICAgKF9fKSAgTyAoPT0pICAgTyhfXykgXCAvKHx8KSBPICAoX18pICBPIChf
XykgICAgKCAgKSBcIC8oX18pIE8gIAogICAgICAgIChvbykoX18pKG9vKShfXykob28pKF9fKShv
bykoX18pKG9vKShfXykoIyMpKF9fKShvbykoX18pKG9vKShfXykKICAgICAgICAgXC8gKG9vKSBc
LyAob28pIFwvICgsLCkgXC8gKG9vKSBcLyAob28pIFwvIChvbykgXC8gKC0tKSBcLyAoT08pCiAg
ICAgICAgKF9fKSBcLyAoX18pIFwvIChfXykgXC8gKF9fKSBcLyAoX18pIFwvIChfXykgXC8gKCws
KSBcLyAoX18pIFwvIAogICAgICAgICgqKikoX18pKC0tKShfXykob28pKF9fKSgwMCkoX18pKG9v
KShfXykob28pKF9fKShvbykoX18pKG9vKShfXykKICAgICAgICAgXC8gKG9vKSBcLyAob28pIFwv
IChvbykgXC8gKG9vKSBcLyAoKiopIFwvIChPTykgXC8gKD8/KSBcLyAob28pCiAgICAgICAgKF9f
KSBcLyAoX18pIFwvIChfXykgXC8gKF9fKSBcLyAoX18pIFwvIChfXykgXC8gKF9fKSBcLyAoX18p
IFwvIAogICAgICAgIChvbykoX18pKG9vKShfXykoQEApKF9fKShvbykoX18pKG9vKShfXykob28p
KF9fKSgtMCkoLCwpKG9vKShfXykKICAgICAgICAgXC8gKG9fKSBcLyAob28pIFwvIChvbykgXC8g
KG8jKSBcLyAob28pIFwvIChvbykgXC8gKG9vKSBcLyAob28pCiAgICAgICAgICAgICBcLyAgICAg
IFwvICAgICAgXC8gICAgICBcLyAgICAgIFwvICAgICAgXC8gICAgICBcLyAgICAgIFwvIAogICAg
ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAg
ICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAg
ICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAoX18pICAgICAgICAgICAg
ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAs
Jy0wMCAgICAgICAgICAgICAgICAgICAgICAgVGhlIExvY2FsIE1vb3NpY2FsIFNvY2lldHkgICAg
ICAKICAgICAgICAgICAvIC9cX3wgICAgICAvICAgICAgICAgICAgICAgICAgICAgICBpbiBDb25j
ZXJ0ICAgICAgICAgICAgICAgCiAgICAgICAgICAvICB8ICAgICAgIF8vX19fX19fX19fX19fX19f
X19fICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICB8ICAgXD09PV5fX3wg
ICAgICAgICAgICAgICAgIF9ffCAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAg
ICBffF9fXyAvXCAgfF9fX19fX19fX19fX19fX19fX198ICAgICAgICAgICAgICAgICAgICAgICAg
ICAgICAgICAgCiAgICAgICAgfD09PT09fCB8ICAgSSAgICAgICAgICAgICAgSSAgICAgICAgICAg
ICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICpJICAgSXwgfCAgIEkgICAgICAgICAg
ICAgIEkgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgSSAgIEle
IF4gICBJICAgICAgICAgICAgICBJICAgICAgICAgICAgICAgICAgICAgLWNmYmQt''')

f = moo
f.category = 'hidden'
f.num_args = 'zero'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def debuglist(moosic, arglist, opts):
    arglist = process_filelist(moosic, arglist, opts)
    for x in arglist:
        print x

f = debuglist
f.category = 'hidden'
f.num_args = 'many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

def debug(moosic, arglist, opts):
    print moosic.debug(' '.join(arglist))

f = debug
f.category = 'hidden'
f.num_args = 'many'
dispatcher[unmangle(f.__name__)] = f

#----------------------------#

del f


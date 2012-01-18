# moosic.server.methods.py - defines and registers the Moosic server methods
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

API_MAJOR_VERSION = 1
API_MINOR_VERSION = 8

# Import from the standard library.
import xmlrpclib, time, os, signal, random, re, errno, operator
from xmlrpclib import Boolean, Binary, True, False

# Define the True and False constants if they don't already exist.
try: True
except NameError: True = 1
try: False
except NameError: False = 0

# Import from my own modules.
import xmlrpc_registry
from xmlrpc_registry import INT, BOOLEAN, DOUBLE, STRING, ARRAY, STRUCT, BASE64
import moosic.utilities
from moosic.utilities import grep, antigrep, splitpath, is_overlapping
import moosic.server.support
from moosic.server.support import data, Log, split_range
from moosic import VERSION

moosicd_methods = xmlrpc_registry.Registry()


def insert(items, position):
    '''Inserts items at a given position in the queue.
 
    Arguments: The first argument is an array of (base64-encoded) strings,
        representing the items to be added.
      * The second argument specifies the position in the queue where the items
        will be inserted.
      * When adding local filenames to the queue, only absolute pathnames should
        be used.  Using relative pathnames would be foolish because the server
        has no idea what the client's current working directory is.
    Return value: Nothing meaningful.
    '''
    for i in items:
        if not hasattr(i, 'data'):
            raise TypeError("Objects of type '%s' cannot be inserted." % \
                            i.__class__.__name__)
    p = position  # Make a shorter alias so that we can fit into 80 colums.
    data.lock.acquire()
    try:
        data.song_queue[p:p] = filter(None, [str(i.data) for i in items])
    finally:
        data.last_queue_update = time.time()
        data.lock.release()
    return True
moosicd_methods.register(insert, [[BOOLEAN, ARRAY, INT]])


def replace(items):
    '''Replaces the contents of the queue with the given items.
 
    This is equivalent to calling clear() and prepend() in succession, except that this
    operation is atomic.
 
    Argument: An array of (base64-encoded) strings, representing the items to be
        added.
      * When adding local filenames to the queue, only absolute pathnames
        should be used.  Using relative pathnames would be foolish because
        the server isn't aware of the client's current working directory.
    Return value: Nothing meaningful.
    '''
    for i in items:
        if not hasattr(i, 'data'):
            raise TypeError("Objects of type '%s' cannot be inserted." % \
                            i.__class__.__name__)
    data.lock.acquire()
    try:
        data.song_queue = filter(None, [str(i.data) for i in items])
    finally:
        data.last_queue_update = time.time()
        data.lock.release()
    return True
moosicd_methods.register(replace, [[BOOLEAN, ARRAY]])


def replace_range(range, items):
    '''Replaces a slice of the contents of the queue with the given items.
 
    This is equivalent to calling cut() and prepend() in succession, except
    that this operation is atomic.
 
    Argument: The first is an array of integers that represents a range.
      * If the range contains a single integer, it will represent all members
        of the queue whose index is greater than or equal to the value of the
        integer.
      * If the range contains two integers, it will represent all members of
        the queue whose index is greater than or equal to the value of the
        first integer and less than the value of the second integer.
      * If the range contains more than two integers, an error will occur.
      * The second argument is an array of (base64-encoded) strings,
        representing the items to be added.
      * When adding local filenames to the queue, only absolute pathnames
        should be used.  Using relative pathnames would be foolish because
        the server isn't aware of the client's current working directory.
    Return value: Nothing meaningful.
    '''
    start, end = split_range(range)
    for i in items:
        if not hasattr(i, 'data'):
            raise TypeError("Objects of type '%s' cannot be inserted." % \
                            i.__class__.__name__)
    data.lock.acquire()
    try:
        data.song_queue[start:end] = filter(None, [str(i.data) for i in items])
    finally:
        data.last_queue_update = time.time()
        data.lock.release()
    return True
moosicd_methods.register(replace, [[BOOLEAN, ARRAY]])


def append(items):
    '''Adds items to the end of the queue.
 
    Argument: An array of (base64-encoded) strings, representing the items to be
        added.
      * When adding local filenames to the queue, only absolute pathnames should
        be used.  Using relative pathnames would be foolish because the server
        has no idea what the client's current working directory is.
    Return value: Nothing meaningful.
    '''
    end = len(data.song_queue)
    return insert(items, end)
moosicd_methods.register(append, [[BOOLEAN, ARRAY]])


def prepend(items):
    '''Adds items to the beginning of the queue.
 
    Argument: An array of (base64-encoded) strings, representing the items to be
        added.
      * When adding local filenames to the queue, only absolute pathnames should
        be used.  Using relative pathnames would be foolish because the server
        has no idea what the client's current working directory is.
    Return value: Nothing meaningful.
    '''
    return insert(items, 0)
moosicd_methods.register(prepend, [[BOOLEAN, ARRAY]])


def clear():
    '''Removes all items from the queue.
 
    Arguments: None.
    Return value: Nothing meaningful.
    '''
    data.lock.acquire()
    try:
        data.song_queue = []
    finally:
        data.last_queue_update = time.time()
        data.lock.release()
    return True
moosicd_methods.register(clear, [[BOOLEAN]])


def sub_all(pattern, replace, range=()):
    '''Performs a global regular expression substitution on the items in the queue.
    
    Arguments: The first is a (base64-encoded) regular expression that specifies
        the text to be replaced.
      * The second argument is the (base64-encoded) string that will be used to
        replace all occurrences of the regular expression within each queue
        item. Any backslash escapes in this string will be processed, including
        special character translation (e.g. "\\n" to newline) and backreferences
        to the substrings matched by individual groups in the pattern.
      * Optionally, an array of integers may be given as a third argument.
        This argument represents a range to which the substitution will be
        limited. This range is interpreted in the same way as the range argument
        in other Moosic methods.
      * If performing a replacement changes an item in the queue into the empty
        string, then it is removed from the queue.
    Return value: Nothing meaningful.
    '''
    start, end = split_range(range)
    if hasattr(pattern, 'data'):
        pattern = str(pattern.data)
    if hasattr(replace, 'data'):
        replace = str(replace.data)
    pattern = re.compile(pattern)
    data.lock.acquire()
    try:
        data.song_queue[start:end] = filter(None, [pattern.sub(replace, item)
                                      for item in data.song_queue[start:end]])
    finally:
        data.last_queue_update = time.time()
        data.lock.release()
    return True
moosicd_methods.register(sub_all, 
        [[BOOLEAN, BASE64, BASE64], [BOOLEAN, BASE64, BASE64, ARRAY]])


def sub(pattern, replace, range=()):
    '''Performs a regular expression substitution on the items in the queue.
    
    Arguments: The first is a (base64-encoded) regular expression that specifies
        the text to be replaced.
      * The second argument is the (base64-encoded) string that will be used to
        replace the first occurrence of the regular expression within each queue
        item. Any backslash escapes in this string will be processed, including
        special character translation (e.g. "\\n" to newline) and backreferences
        to groups within the match.
      * Optionally, an array of integers may be given as a third argument.
        This argument represents a range to which the substitution will be
        limited. This range is interpreted in the same way as the range argument
        in other Moosic methods.
      * If performing a replacement changes an item in the queue into the empty
        string, then it is removed from the queue.
    Return value: Nothing meaningful.
    '''
    start, end = split_range(range)
    if hasattr(pattern, 'data'):
        pattern = str(pattern.data)
    if hasattr(replace, 'data'):
        replace = str(replace.data)
    pattern = re.compile(pattern)
    data.lock.acquire()
    try:
        data.song_queue[start:end] = filter(None, [pattern.sub(replace, item, 1)
                                      for item in data.song_queue[start:end]])
    finally:
        data.last_queue_update = time.time()
        data.lock.release()
    return True
moosicd_methods.register(sub, 
        [[BOOLEAN, BASE64, BASE64], [BOOLEAN, BASE64, BASE64, ARRAY]])


def shuffle(range=()):
    '''Rearrange the contents of the queue into a random order.
 
    Arguments: Either none, or an array of integers that represents a range.
      * If no range is given, the whole list is affected.
      * If the range contains a single integer, it will represent all members
        of the queue whose index is greater than or equal to the value of the
        integer.
      * If the range contains two integers, it will represent all members of
        the queue whose index is greater than or equal to the value of the
        first integer and less than the value of the second integer.
      * If the range contains more than two integers, an error will occur.
    Return value: Nothing meaningful.
    '''
    start, end = split_range(range)
    altered_slice = data.song_queue[start:end]
    random.shuffle(altered_slice)
    data.lock.acquire()
    try:
        data.song_queue[start:end] = altered_slice
    finally:
        data.last_queue_update = time.time()
        data.lock.release()
    return True
moosicd_methods.register(shuffle, [[BOOLEAN], [BOOLEAN, ARRAY]])


def sort(range=()):
    '''Arranges the contents of the queue into sorted order.
 
    Arguments: Either none, or an array of integers that represents a range.
      * If no range is given, the whole list is affected.
      * If the range contains a single integer, it will represent all members
        of the queue whose index is greater than or equal to the value of the
        integer.
      * If the range contains two integers, it will represent all members of
        the queue whose index is greater than or equal to the value of the
        first integer and less than the value of the second integer.
      * If the range contains more than two integers, an error will occur.
    Return value: Nothing meaningful.
    '''
    start, end = split_range(range)
    altered_slice = data.song_queue[start:end]
    altered_slice.sort()
    data.lock.acquire()
    try:
        data.song_queue[start:end] = altered_slice
    finally:
        data.last_queue_update = time.time()
        data.lock.release()
    return True
moosicd_methods.register(sort, [[BOOLEAN], [BOOLEAN, ARRAY]])


def reverse(range=()):
    '''Reverses the order of the items in the queue.
 
    Arguments: Either none, or an array of integers that represents a range.
      * If no range is given, the whole list is affected.
      * If the range contains a single integer, it will represent all members
        of the queue whose index is greater than or equal to the value of the
        integer.
      * If the range contains two integers, it will represent all members of
        the queue whose index is greater than or equal to the value of the
        first integer and less than the value of the second integer.
      * If the range contains more than two integers, an error will occur.
    Return value: Nothing meaningful.
    '''
    start, end = split_range(range)
    altered_slice = data.song_queue[start:end]
    altered_slice.reverse()
    data.lock.acquire()
    try:
        data.song_queue[start:end] = altered_slice
    finally:
        data.last_queue_update = time.time()
        data.lock.release()
    return True
moosicd_methods.register(reverse, [[BOOLEAN], [BOOLEAN, ARRAY]])


def putback():
    '''Places the currently playing song at the beginning of the queue.
 
    Arguments: None.
    Return value: Nothing meaningful.
    '''
    if data.current_song:
        data.lock.acquire()
        try:
            data.song_queue.insert(0, data.current_song)
        finally:
            data.last_queue_update = time.time()
            data.lock.release()
    return True
moosicd_methods.register(putback, [[BOOLEAN]])


def current():
    '''Returns the name of the currently playing song.
 
    Arguments: None.
    Return value: The name of the currently playing song.
    '''
    return Binary(data.current_song)
moosicd_methods.register(current, [[BASE64]])


def list(range=()):
    '''Lists the song queue's contents. If a range is specified, only the
    items that fall within that range are listed.
 
    Arguments: Either none, or an array of integers that represents a range.
      * If no range is given, the whole list is returned.
      * If the range contains a single integer, it will represent all members
        of the queue whose index is greater than or equal to the value of the
        integer.
      * If the range contains two integers, it will represent all members of
        the queue whose index is greater than or equal to the value of the
        first integer and less than the value of the second integer.
      * If the range contains more than two integers, an error will occur.
    Return value: An array of (base64-encoded) strings, representing the
        selected range from the song queue's contents.
    '''
    start, end = split_range(range)
    return [Binary(i) for i in data.song_queue[start:end]]
moosicd_methods.register(list, [[ARRAY], [ARRAY, ARRAY]])


def indexed_list(range=()):
    '''Lists the song queue's contents. If a range is specified, only the
    items that fall within that range are listed.
 
    This differs from list() only in its return value, and is useful when you
    want to know the starting position of your selected range within the song
    queue (which can be different than the starting index of the specified range
    if, for example, the starting index is a negative integer).
 
    Arguments: Either none, or an array of integers that represents a range.
      * If no range is given, the whole list is returned.
      * If the range contains a single integer, it will represent all members
        of the queue whose index is greater than or equal to the value of the
        integer.
      * If the range contains two integers, it will represent all members of
        the queue whose index is greater than or equal to the value of the
        first integer and less than the value of the second integer.
      * If the range contains more than two integers, an error will occur.
    Return value: A struct with two elements. This first is "list", an array of
        (base64-encoded) strings, representing the selected range from the song
        queue's contents. The second is "start", an integer index value that
        represents the position of the first item of the returned list in the
        song queue.
    '''
    start, end = split_range(range)
    list = [Binary(i) for i in data.song_queue[start:end]]
    start_index = start
    if start_index < 0:
        start_index = len(data.song_queue) + start_index
        if start_index < 0:
            start_index = 0
    return {'start':start_index, 'list':list}
moosicd_methods.register(indexed_list, [[STRUCT], [STRUCT, ARRAY]])


#def packed_list(range=()):
#    '''Lists the song queue's contents. If a range is specified, only the
#    items that fall within that range are listed.
# 
#    This differs from list() only in its return value, and is useful since it is
#    much faster when the song queue is very large.
# 
#    Arguments: Either none, or an array of integers that represents a range.
#      * If no range is given, the whole list is returned.
#      * If the range contains a single integer, it will represent all members
#        of the queue whose index is greater than or equal to the value of the
#        integer.
#      * If the range contains two integers, it will represent all members of
#        the queue whose index is greater than or equal to the value of the
#        first integer and less than the value of the second integer.
#      * If the range contains more than two integers, an error will occur.
#    Return value: A single (base64-encoded) string which contains the selected
#        range from the song queue's contents in a "packed" form. That is, if
#        you split the return value (after base64-decoding it), using '\\0' as
#        the delimiter, a list of the selected queue items will result.  ('\\0'
#        denotes the character whose ASCII ordinal is 0.)
#    '''
#    start, end = split_range(range)
#    return Binary('\0'.join(data.song_queue[start:end]))
#moosicd_methods.register(packed_list, [[BASE64], [BASE64, ARRAY]])


def halt_queue():
    '''Stops any new songs from being played. Use run_queue() to reverse this
    state.
 
    Arguments: None.
    Return value: Nothing meaningful.
    '''
    data.lock.acquire()
    try:
        data.qrunning = False
    finally:
        data.lock.release()
    return True
moosicd_methods.register(halt_queue, [[BOOLEAN]])
haltqueue = halt_queue
moosicd_methods.register(halt_queue, [[BOOLEAN]], "haltqueue")


def run_queue():
    '''Allows new songs to be played again after halt_queue() has been called.
 
    Arguments: None.
    Return value: Nothing meaningful.
    '''
    data.lock.acquire()
    try:
        data.qrunning = True
    finally:
        data.lock.release()
    return True
moosicd_methods.register(run_queue, [[BOOLEAN]])
runqueue = run_queue
moosicd_methods.register(run_queue, [[BOOLEAN]], "runqueue")


def pause():
    '''Pauses the currently playing song.
 
    Arguments: None.
    Return value: Nothing meaningful.
    '''
    data.lock.acquire()
    try:
        if data.current_song and data.player_pid:
            try:
                os.kill(data.player_pid, signal.SIGTSTP)
                time.sleep(0.10)
                os.kill(data.player_pid, signal.SIGSTOP)
            except OSError, e:
                e.strerror += ' (in method "pause")'
                raise e
            if data.paused == False:
                data.last_pause_event = time.time()
                #data.start_stop_times.append( time.time() )  # old algorithm
            data.paused = True
    finally:
        data.lock.release()
    return True
moosicd_methods.register(pause, [[BOOLEAN]])


def unpause():
    '''Unpauses the current song.
 
    Arguments: None.
    Return value: Nothing meaningful.
    '''
    data.lock.acquire()
    try:
        if data.current_song and data.player_pid:
            try:
                os.kill(data.player_pid, signal.SIGCONT)
            except OSError, e:
                if e.errno == errno.ESRCH:
                    data.player_pid = None
                else:
                    e.strerror += ' (in method "unpause")'
                    raise e
            if data.paused == True:
                data.current_paused_time += (time.time() - data.last_pause_event)
                #data.start_stop_times.append( -time.time() )  # old algorithm
            data.paused = False
    finally:
        data.lock.release()
    return True
moosicd_methods.register(unpause, [[BOOLEAN]])


def toggle_pause():
    '''Pauses the current song if it is playing, and unpauses if it is paused.
 
    Arguments: None.
    Return value: Nothing meaningful.
    '''
    data.lock.acquire()
    try:
        if data.current_song and data.player_pid:
            if data.paused:
                unpause()
            else:
                pause()
    finally:
        data.lock.release()
    return True
moosicd_methods.register(toggle_pause, [[BOOLEAN]])


def is_looping():
    '''Tells you whether loop mode is on or not.
 
    If loop mode is on, songs are returned to the end of the song queue after
    they finish playing.  If loop mode is off, songs that have finished playing
    are not returned to the queue.
 
    Arguments: None.
    Return value: True if loop mode is set, False if it is not.
    '''
    return data.loop_mode
moosicd_methods.register(is_looping, [[BOOLEAN]])


def set_loop_mode(value):
    '''Turns loop mode on or off.
 
    If loop mode is on, songs are returned to the end of the song queue after
    they finish playing.  If loop mode is off, songs that have finished playing
    are not returned to the queue.
 
    Arguments: True if you want to turn loop mode on, False if you want to turn
        it off.
    Return value: Nothing meaningful.
    '''
    data.lock.acquire()
    try:
        if value:
            data.loop_mode = True
        else:
            data.loop_mode = False
    finally:
        data.lock.release()
    return True
moosicd_methods.register(set_loop_mode, [[BOOLEAN, BOOLEAN]])


def toggle_loop_mode():
    '''Turns loop mode on if it is off, and turns it off if it is on.
 
    If loop mode is on, songs are returned to the end of the song queue after
    they finish playing.  If loop mode is off, songs that have finished playing
    are not returned to the queue.
 
    Arguments: None.
    Return value: Nothing meaningful.
    '''
    data.lock.acquire()
    try:
        if data.loop_mode:
            data.loop_mode = False
        else:
            data.loop_mode = True
    finally:
        data.lock.release()
    return True
moosicd_methods.register(toggle_loop_mode, [[BOOLEAN]])


def skip():
    '''Skips the rest of the current song to play the next song in the queue.
    This only has an effect if there actually is a current song.
 
    Arguments: None.
    Return value: Nothing meaningful.
    '''
    if data.current_song and data.player_pid:
        # ogg123 behaves very stupidly when it gets a TERM signal, so it needs
        # to be handled specially. This logic for determining when to apply this
        # special case is complicated, and interferes with readability, and is
        # yucky and evil and sloppy, and makes assumptions which are not
        # necessarily true. I hate you, ogg123.
        command = None
        for regex, cmd in data.config:
            if regex.search(data.current_song):
                command = cmd[:]
                break
        try:
            if command and command[0] == 'ogg123':
                os.kill(data.player_pid, signal.SIGINT)
            else:
                os.kill(data.player_pid, signal.SIGTERM)
        except OSError, e:
            e.strerror += ' (in method "skip")'
            raise e
        # Unpause the song player, so that termination takes place right away
        # (instead of having to wait until the song player somehow happens to
        # receive a CONT signal).
        unpause()
    return True
moosicd_methods.register(skip, [[BOOLEAN]])


def next(howmany=1):
    '''Stops the current song (if any), and jumps ahead to a song that is
    currently in the queue. The skipped songs are recorded in the history as if
    they had been played. When called without arguments, this behaves very
    much like the skip() method, except that it will have an effect even if
    nothing is currently playing.
 
    Arguments: A single integer that tells how far forward into the song queue
        to advance. A value of 1 will cause the first song in the queue to play,
        2 will cause the second song in the queue to play, and so on. If no
        argument is given, a value of 1 is assumed.
    Return value: Nothing meaningful.
    '''
    data.lock.acquire()
    try:
        #if not data.current_song: howmany -= 1
        queue_was_running = is_queue_running()
        stop()
        for i in range(howmany):
            if not data.song_queue: break
            song = data.song_queue.pop(0)
            if data.loop_mode:
                data.song_queue.append(song)
            data.history.append((song, data.song_start_event, time.time()))
        while len(data.history) > data.max_hist_size:
            data.history.pop(0)
    finally:
        data.last_queue_update = time.time()
        if queue_was_running:
            run_queue()
        data.lock.release()
    return True
moosicd_methods.register(next, [[BOOLEAN], [BOOLEAN, INT]])


def previous(howmany=1):
    '''Stops the current song (if any), removes the most recently played song
    from the history, and puts these songs at the head of the queue. When loop
    mode is on, the songs at the tail of the song queue are used instead of the
    most recently played songs in the history.
 
    Arguments: A single integer that tells how far back in the history list to
        retreat. A value of 1 will cause the most recent song to play, 2 will
        cause the second most recent song to play, and so on. If no argument is
        given, a value of 1 is assumed.
    Return value: Nothing meaningful.
    '''
    data.lock.acquire()
    try:
        queue_was_running = is_queue_running()
        stop()
        for i in range(howmany):
            if not data.loop_mode:
                if not data.history: break
                data.song_queue.insert(0, data.history.pop()[0])
            else:
                data.song_queue.insert(0, data.song_queue.pop())
    finally:
        data.last_queue_update = time.time()
        if queue_was_running:
            run_queue()
        data.lock.release()
    return True
moosicd_methods.register(previous, [[BOOLEAN], [BOOLEAN, INT]])


def stop():
    '''Stops playing the current song and stops new songs from playing. The
    current song is returned to the head of the song queue and is not recorded
    in the history list. If loop mode is on, the current song won't be placed at
    the end of the song queue when it is stopped.
 
    Arguments: None.
    Return value: Nothing meaningful.
    '''
    putback()
    halt_queue()
    if data.current_song:
        data.ignore_song_finish = True
    skip()
    return True
moosicd_methods.register(stop, [[BOOLEAN]])


def remove(regexp, range=()):
    '''Removes all items that match the given regular expression.
 
    Arguments: A regular expression that specifies which items to remove.
      * Optionally, an array of integers may be given as a second argument.
        This argument represents a range to which the removal will be limited.
      * If the range contains a single integer, it will represent all members
        of the queue whose index is greater than or equal to the value of the
        integer.
      * If the range contains two integers, it will represent all members of
        the queue whose index is greater than or equal to the value of the
        first integer and less than the value of the second integer.
      * If the range contains more than two integers, an error will occur.
    Return value: Nothing meaningful.
    '''
    start, end = split_range(range)
    data.lock.acquire()
    try:
        if hasattr(regexp, 'data'):
            regexp = regexp.data
        data.song_queue[start:end] = antigrep(regexp, data.song_queue[start:end])
    finally:
        data.last_queue_update = time.time()
        data.lock.release()
    return True
moosicd_methods.register(remove, [[BOOLEAN, BASE64], [BOOLEAN, BASE64, ARRAY]])


def filter_(regexp, range=()):
    '''Removes all items that don't match the given regular expression.
 
    Arguments: A regular expression that specifies which items to keep.
      * Optionally, an array of integers may be given as a second argument.
        This argument represents a range to which the filtering will be
        limited.
      * If the range contains a single integer, it will represent all members
        of the queue whose index is greater than or equal to the value of the
        integer.
      * If the range contains two integers, it will represent all members of
        the queue whose index is greater than or equal to the value of the
        first integer and less than the value of the second integer.
      * If the range contains more than two integers, an error will occur.
    Return value: Nothing meaningful.
    '''
    start, end = split_range(range)
    data.lock.acquire()
    try:
        if hasattr(regexp, 'data'):
            regexp = regexp.data
        data.song_queue[start:end] = grep(regexp, data.song_queue[start:end])
    finally:
        data.last_queue_update = time.time()
        data.lock.release()
    return True
moosicd_methods.register(filter_, [[BOOLEAN, BASE64], [BOOLEAN, BASE64, ARRAY]], 'filter')


def move(range, dest):
    '''Moves a range of items to a new position within the queue.
 
    Arguments: The first argument is an array of integers that represents a
        range of items to be moved. 
      * If the range contains a single integer, it will represent all members
        of the queue whose index is greater than or equal to the value of the
        integer.
      * If the range contains two integers, it will represent all members of
        the queue whose index is greater than or equal to the value of the
        first integer and less than the value of the second integer.
      * If the range contains more than two integers, an error will occur.
      * The second argument, "destination", specifies the position in the queue
        where the items will be moved.
    Return value: Nothing meaningful.
    '''
    start, end = split_range(range)
    # Use an out-of-bound piece of data to mark the old positions of moved
    # items.  Since the playlist normally only contains strings, any non-string
    # value will work as an effective marker.
    mark = None
    data.lock.acquire()
    try:
        # Copy the items to be moved.
        stuff_to_move = data.song_queue[start:end]
        # "Delete" the items from their old position by replacing them with
        # marker values. Regular removal isn't done at this point because we
        # don't want to invalidate the meaning of our destination index.
        data.song_queue[start:end] = [mark]*len(stuff_to_move)
        # Place the collected items at their destination.
        data.song_queue[dest:dest] = stuff_to_move
        # Remove the markers.
        data.song_queue = [item for item in data.song_queue if item is not mark]
    finally:
        data.last_queue_update = time.time()
        data.lock.release()
    return True
moosicd_methods.register(move, [[BOOLEAN, ARRAY, INT]])


def move_list(indices, dest):
    '''Moves the items referenced by a list of positions to a new position.
    
    Arguments: The first argument is an array of integers that represents a
        list of the positions of the items to be moved. 
      * The second argument, "destination", specifies the position in the queue
        where the items will be moved.
    Return value: Nothing meaningful.
    '''
    # Use an out-of-bound piece of data to mark the old positions of moved
    # items.  Since the playlist normally only contains strings, any non-string
    # value will work as an effective marker.
    mark = None
    data.lock.acquire()
    try:
        stuff_to_move = []
        for i in indices:
            # Copy each item to be moved.
            stuff_to_move.append(data.song_queue[i])
            # "Delete" each item from its old position by replacing it with a
            # marker. Regular removal isn't done at this point because we don't
            # want to invalidate the meaning of our destination index.
            data.song_queue[i] = mark
        # Place the collected items at their destination.
        data.song_queue[dest:dest] = stuff_to_move
        # Remove the markers.
        data.song_queue = [item for item in data.song_queue if item is not mark]
    finally:
        data.last_queue_update = time.time()
        data.lock.release()
    return True
moosicd_methods.register(move_list, [[BOOLEAN, ARRAY, INT]])


def swap(range_A, range_B):
    '''Swaps the items contained in one range with the items contained in the
    other range.
    
    Return value: Nothing meaningful.
    '''
    A = split_range(range_A)
    B = split_range(range_B)
    data.lock.acquire()
    try:
        # Normalize the case where negative numbers are used as range indices.
        n = len(data.song_queue)
        if A[0] < 0:   A[0] = n - A[0]
        if A[1] < 0:   A[1] = n - A[1]
        if B[0] < 0:   B[0] = n - B[0]
        if B[1] < 0:   B[1] = n - B[1]
        # Forbid overlapping ranges.
        if is_overlapping(A, B, len(data.song_queue)):
            raise ValueError("Overlapping ranges may not be swapped: %s %s" % (A, B))
        # Make sure range A is closer to the head of the queue than range B.
        if A > B:
            A, B = B, A
        # Split the queue into various slices, delineated by the given ranges.
        prefix  = data.song_queue[:A[0]]
        slice_A = data.song_queue[A[0]:A[1]]
        infix   = data.song_queue[A[1]:B[0]]
        slice_B = data.song_queue[B[0]:B[1]]
        suffix  = data.song_queue[B[1]:]
        # Piece the slices back together, swapping A with B.
        data.song_queue = prefix + slice_B + infix + slice_A + suffix
    finally:
        data.last_queue_update = time.time()
        data.lock.release()
    return True
moosicd_methods.register(swap, [[BOOLEAN, ARRAY, ARRAY]])


def cut(range):
    '''Remove all queued items that fall within the given range.
 
    Arguments: An array of integers that represents a range.
      * If the range contains a single integer, it will represent all members
        of the queue whose index is greater than or equal to the value of the
        integer.
      * If the range contains two integers, it will represent all members of
        the queue whose index is greater than or equal to the value of the
        first integer and less than the value of the second integer.
      * If the range contains more than two integers, an error will occur.
    Return value: Nothing meaningful.
    '''
    start, end = split_range(range)
    data.lock.acquire()
    try:
        del data.song_queue[start:end]
    finally:
        data.last_queue_update = time.time()
        data.lock.release()
    return True
moosicd_methods.register(cut, [[BOOLEAN, ARRAY]])


def cut_list(indices):
    '''Removes the items referenced by a list of positions within the queue.
    
    Arguments: An array of integers that represents a list of the positions of
        the items to be removed. 
    Return value: Nothing meaningful.
    '''
    mark = None
    data.lock.acquire()
    try:
        for i in indices:
            # Replace the item at each index with a marker. This is done instead
            # of removing the item from the list in order to prevent the
            # invalidation of later index values.
            data.song_queue[i] = mark
        # Remove the markers now that all indices have been handled.
        data.song_queue = [item for item in data.song_queue if item is not mark]
    finally:
        data.last_queue_update = time.time()
        data.lock.release()
    return True
moosicd_methods.register(cut_list, [[BOOLEAN, ARRAY]])


def crop(range):
    '''Remove all queued items that do not fall within the given range.
 
    Arguments: An array of integers that represents a range.
      * If the range contains a single integer, it will represent all members
        of the queue whose index is greater than or equal to the value of the
        integer.
      * If the range contains two integers, it will represent all members of
        the queue whose index is greater than or equal to the value of the
        first integer and less than the value of the second integer.
      * If the range contains more than two integers, an error will occur.
    Return value: Nothing meaningful.
    '''
    start, end = split_range(range)
    data.lock.acquire()
    try:
        data.song_queue = data.song_queue[start:end]
    finally:
        data.last_queue_update = time.time()
        data.lock.release()
    return True
moosicd_methods.register(crop, [[BOOLEAN, ARRAY]])


def crop_list(indices):
    '''Removes all items except for those referenced by a list of positions.
    
    Arguments: An array of integers that represents a list of the positions of
        the items to be kept. 
    Return value: Nothing meaningful.
    '''
    data.lock.acquire()
    try:
        data.song_queue = [data.song_queue[i] for i in indices]
    finally:
        data.last_queue_update = time.time()
        data.lock.release()
    return True
moosicd_methods.register(crop_list, [[BOOLEAN, ARRAY]])


def history(limit=0):
    '''Returns a list of the items that were recently played.
 
    Arguments: If a positive integer argument is given, then no more than that
        number of entries will be returned.  If a number is not specified, or if
        zero is given, then the entire history is returned.  The result is
        undefined if a negative integer argument is given (but does not raise an
        exception).
    Return value: An array of triples, each representing a song that was played
        along with the times that it started and finished playing.
      * The first member of the pair is a (base64-encoded) string which
        represents the song that was previously played.
      * The second member of the pair is a floating point number which
        represents the time that the song started playing in seconds since the
        epoch.
      * The third member of the pair is a floating point number which
        represents the time that the song finished playing in seconds since the
        epoch.
    '''
    return [(Binary(item), starttime, endtime)
            for item, starttime, endtime in data.history[-limit:]]
moosicd_methods.register(history, [[ARRAY], [ARRAY, INT]])


def get_history_limit():
    '''Gets the limit on the size of the history list stored in memory.
 
    Arguments: None.
    Return value: The maximum number of history entries that the server will
        remember.
    '''
    return data.max_hist_size
moosicd_methods.register(get_history_limit, [[INT]])


def set_history_limit(size):
    '''Sets the limit on the size of the history list stored in memory.
 
    This will irrevocably discard history entries if the new limit is lower than
    the current size of the history list.
 
    Arguments: The new maximum number of history entries. If this value is
        negative, the history limit will be set to zero.
    Return value: Nothing meaningful.
    '''
    data.lock.acquire()
    try:
        data.max_hist_size = int(size)
        if data.max_hist_size < 0:
            data.max_hist_size = 0
        while len(data.history) > data.max_hist_size:
            data.history.pop(0)
    finally:
        data.lock.release()
    return True
moosicd_methods.register(set_history_limit, [[BOOLEAN, INT]])


def die():
    '''Tells the server to terminate itself.
 
    Arguments: None.
    Return value: Nothing meaningful.
    '''
    data.quitFlag = True  # Tell the queue consumer to quit.
    if data.current_song:
        data.ignore_song_finish = True
    skip()  # Stop the current song.
    # There's no need to do anything to make the request handler quit, since it
    # will terminate as soon as the queue consumer is gone.
    return True
moosicd_methods.register(die, [[BOOLEAN]])


def is_paused():
    '''Tells you whether the current song is paused or not.
 
    Arguments: None.
    Return value: True if the current song is paused, otherwise False.
    '''
    return Boolean(data.paused)
moosicd_methods.register(is_paused, [[BOOLEAN]])


def is_queue_running():
    '''Tells you whether the queue consumption (advancement) is activated.
 
    Arguments: None.
    Return value: True if new songs are going to be played from the queue after
        the current song is finished, otherwise False.
    '''
    return Boolean(data.qrunning)
moosicd_methods.register(is_queue_running, [[BOOLEAN]])


def queue_length():
    '''Returns the number of items in the song queue.
 
    Arguments: None.
    Return value: The number of items in the song queue.
    '''
    return len(data.song_queue)
moosicd_methods.register(queue_length, [[INT]])

length = queue_length
moosicd_methods.register(queue_length, [[INT]], "length")


def current_time():
    # This alternate version works in constant time, rather than depending on
    # the length of an arbitrarily long list of play/pause events.
    '''Returns the amount of time that the current song has been playing.
 
    Arguments: None.
    Return value: The number of seconds that the current song has been playing.
    '''
    if not data.current_song:
        return 0
    if data.paused:
        return data.last_pause_event - data.song_start_event - data.current_paused_time
    else:
        return time.time() - data.song_start_event - data.current_paused_time
moosicd_methods.register(current_time, [[DOUBLE]])


def version():
    '''Returns the Moosic server's version string.
 
    Arguments: None.
    Return value: The version string for the Moosic server.
    '''
    return VERSION
moosicd_methods.register(version, [[STRING]])


def api_version():
    '''Returns the version number for the API that the server implements.
 
    Arguments: None.
    Return value: The version number, which is a 2-element array of
        integers.  The first element is the major version, and the second
        element is the minor version.
    '''
    return API_MAJOR_VERSION, API_MINOR_VERSION
moosicd_methods.register(api_version, [[ARRAY]])


def reconfigure():
    '''Tells the server to reread its player configuration file.
 
    Arguments: None.
    Return value: Nothing meaningful.
    '''
    try:
        data.lock.acquire()
        try:
            data.config = moosic.server.support.readConfig(data.conffile)
        finally:
            data.lock.release()
    except IOError, e:
        data.log(Log.ERROR,
            "The configuration file could not be reloaded!\n" +
            "%s: %s" % (data.conffile, e))
        raise e
    return True
moosicd_methods.register(reconfigure, [[BOOLEAN]])


def showconfig():
    '''Returns a textual description of the server's player configuration.
 
    Arguments: None.
    Return value: A (base64-encoded) string that shows which programs will be
        used to play the various file-types recognized by the Moosic server.
    '''
    return Binary(moosic.server.support.strConfig(data.config))
moosicd_methods.register(showconfig, [[BASE64]])


def getconfig():
    '''Returns a list of the server's filetype-player associations.
    
    Arguments: None.
    Return value: An array of pairs. The first element of each pair is a
        (base64-encoded) string that represents a regular expression pattern,
        and the second element is a (base64-encoded) string that represents the
        system command that should be used to handle songs that match the
        corresponding pattern.
    '''
    # For full generality, the Binary() wrapper is used to base64-encode the
    # strings in this list.  This is less convenient, and it seems unlikely that
    # either the pattern or the command would contain non-ASCII characters...
    # but you can never be sure.  Better safe than sorry.
    return [(Binary(regex.pattern), Binary(' '.join(cmd))) for regex, cmd in data.config]
moosicd_methods.register(getconfig, [[ARRAY]])


def no_op():
    '''Does nothing, successfully.
 
    Arguments: None.
    Return value: Nothing meaningful.
    '''
    return True
moosicd_methods.register(no_op, [[BOOLEAN]])


def last_queue_update():
    '''Returns the time at which the song queue was last modified.
 
    This method is intended for use by GUI clients that don't want to waste time
    downloading the entire contents of the song queue if it hasn't changed.
    
    Arguments: None.
    Return value: A floating-point number that represents time as the number of
        seconds since the epoch.
    '''
    return data.last_queue_update
moosicd_methods.register(last_queue_update, [[DOUBLE]])


# The following additions make the proxy objects for the server act like normal
# Python objects when subjected to certain common operations.

moosicd_methods.register(queue_length, [[INT]], "__len__")
moosicd_methods.register(lambda:1, [[BOOLEAN]], "__nonzero__")


#def __getitem__(index):
#    """This is experimental.  Ignore it.
#    """
#    return Binary(data.song_queue[index])
#moosicd_methods.register(__getitem__, [[BASE64, INT]])
##moosicd_methods.register(__getitem__, [[BASE64, INT]], "getitem")


#def __getslice__(start, stop):
#    """This is experimental.  Ignore it.
#    """
#    return [Binary(i) for i in data.song_queue[start:stop]]
#moosicd_methods.register(__getslice__, [[ARRAY, INT]])
##moosicd_methods.register(__getslice__, [[ARRAY, INT]], "getslice")


# XXX: This is intended for debugging purposes, and should probably be disabled
# when it is time to make a release.
#def echo(arg):
#    '''Returns whatever is passed to it.
#    '''
#    return arg
# This type signature is a bit of a lie.
#moosicd_methods.register(echo, [[BASE64, BASE64]])


#def debug(code):
#    '''Evaluates arbitrary code within the context of the server and returns the result.
#    
#    This method is very powerful and dangerous and is only intended to be used
#    for the purpose of debugging the server.  It should be disabled in
#    production releases because it is a GIANT GAPING SECURITY HOLE.  Needless to
#    say, it is not an official part of the Moosic server API.
#    
#    Just once more, for dramatic effect:
#    XXX   GIANT GAPING SECURITY HOLE!!!   XXX
#    '''
#    if hasattr(code, 'data'):
#        code = str(code.data)
#    return Binary('%s' % eval(code))
#moosicd_methods.register(debug, [[BASE64, BASE64]])

# moosic.server.support.py - classes and functions that support moosicd
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

import sys, os, os.path, string, threading, time, socket, traceback, errno
import SocketServer, SimpleXMLRPCServer

# Define the True and False constants if they don't already exist.
try: True
except NameError: True = 1
try: False
except NameError: False = 0

__all__ = ('data', 'readConfig', 'strConfig', 'getConfigFile', 'split_range',
           'Log', 'UnixMoosicRequestHandler', 'TcpMoosicRequestHandler',
           'UnixMoosicServer', 'TcpMoosicServer')

class DataStore:
    """A convenient place to store the data maintained by the Moosic server.
    """
    def __init__(self):
        self.__dict__['doing_init'] = True
        #------ data that should be remembered if moosicd is restarted ------#
        # 'song_queue' is a list of all the songs that are waiting to be played.
        self.song_queue = []

        # 'qrunning' is used for controlling the state of the thread that is in
        # charge of advancing through the playlist, a.k.a. the queue consumer.
        # If it is true, then the queue consumer will continue advancing through
        # the playlist, otherwise the queue consumer will be idle.
        self.qrunning = True

        # 'loop_mode' is a flag which, if true, causes the queue consumer to
        # place items at the end of the queue when they finish playing instead
        # of throwing them away.
        self.loop_mode = False

        # 'history' is a list of all the songs that have been played, along with
        # timestamps indicating when each song started and finished playing.
        self.history = []

        # 'max_hist_size' sets the limit on the size of the history list stored
        # in memory.
        self.max_hist_size = 50

        #------ data that should not be remembered if moosicd is restarted ------#
        # 'moosic_server' is a the SocketServer object that is used to listen
        # for and handle requests from Moosic clients.
        self.moosic_server = None

        # 'current_song' is the song that is currently playing.  If no song is
        # currently playing, this will be the empty string.
        self.current_song = ''

        # 'player_pid' is the process ID of the process that is playing the
        # current song.
        self.player_pid = None

        # 'paused' is a flag that keeps track of whether the song player has
        # been paused.
        self.paused = False

        # 'lock' is used to synchronize write-access to the other global
        # variables.
        self.lock = threading.RLock()

        # 'quitFlag' is used to let the different parts of moosicd tell each
        # other that it is time to shut down.  When the queue consumer sees that
        # this flag is true, it will terminate itself.
        self.quitFlag = False

        # 'config' is a list of associations between filename patterns and
        # player programs.
        self.config = []

        # 'confdir' is the directory where moosicd stores its log files,
        # configuration files, and socket files. The default configuration
        # directory is set here.
        self.confdir = os.path.join(os.getenv('HOME', '/tmp'), '.moosic')

        # 'conffile' is the file which contains a textual description of the
        # associations stored in the 'config' variable.
        self.conffile = None

        # 'log' is a callable that is used to record events that occur in
        # moosicd that might be of interest to the outside world. It takes two
        # arguments: (1) an integer that indicates the priority of the event
        # that occurred, and (2) a string that describes the event.
        self.log = lambda priority, message: None  # <-- a dummy logger.

        # 'start_stop_times' is a list of times at which either a "song pause"
        # event or a "song play/continue" event occurred. An item in this list
        # with an even index represent the time (measured in the number of
        # seconds since the epoch) at which a "play" event occurred, while one
        # with an odd index are the time at which a "pause" event occurred.
        # These values can be used to compute the amount of time that the
        # current song has been playing.
        self.start_stop_times = []

        # 'song_start_event' is the point in time (represented by a number of
        # seconds since the epoch) that the current song started playing.
        self.song_start_event = 0

        # 'last_pause_event' is the point in time (in seconds since the epoch)
        # at which the current song was most recently paused.
        self.last_pause_event = 0

        # 'current_paused_time' is the length of the interval of time (measured
        # in number of seconds) that the current song has spent in the paused
        # state.
        self.current_paused_time = 0

        # 'last_queue_update' is the time at which the song queue was last
        # modified. It a floating-point number that represents time as the
        # number of seconds since the epoch.
        self.last_queue_update = time.time()

        # 'ignore_song_finish' is a flag that is used to indicate to the queue
        # consumer that the current song should not be put in the history when
        # the song finishes playing.
        self.ignore_song_finish = False

        # 'extra_moosic_server' is a SocketServer object that is used only when
        # moosicd is listening for requests through both a Unix socket and an IP
        # socket.
        self.extra_moosic_server = None

        # 'music_root' is the name of the directory in which the file listing
        # API functions are permitted.  If this is the empty string, then file
        # listing will not be permitted at all.
        self.music_root = os.path.realpath('/data/music') # DEBUG
        #self.music_root = None

        del self.doing_init

    def __setattr__(self, name, value):
        # Override __setattr__ to prevent adding new attributes that weren't
        # created in the constructor.
        if not hasattr(self, name) and not hasattr(self, 'doing_init'):
            raise AttributeError("'%s' object has no attribute '%s'" %
                    (self.__class__.__name__, name))
        else:
            self.__dict__[name] = value

    def getstate(self):
        # Only save certain attributes.
        saved_state = {}
        attrs_to_save = (
                'song_queue',
                'qrunning',
                'loop_mode',
                'history',
                'max_hist_size',
            )
        for attr in attrs_to_save:
            saved_state[attr] = getattr(self, attr)
        # Normalize boolean objects into the standard boolean type.
        # (Avoid saving unusual boolean objects like xmlrpclib.Boolean.)
        saved_state['qrunning'] = bool(saved_state['qrunning'])
        saved_state['loop_mode'] = bool(saved_state['loop_mode'])
        # The current song will be put back at the head of the queue if and only
        # if the queue consumer is active.
        if self.qrunning and self.current_song:
            saved_state["song_queue"] = [self.current_song] + saved_state["song_queue"]
        return saved_state

    def setstate(self, saved_state):
        # Merge the saved attributes in with the existing ones.
        self.__dict__.update(saved_state)

data = DataStore()


def readConfig(filename):
    """Parses a moosicd configuration file and returns the data within.
 
    The "filename" argument specifies the name of the file from which to read
    the configuration. This function returns a list of 2-tuples which associate
    regular expression objects to the commands that will be used to play files
    whose names are matched by the regexps.
    """
    import re, fileinput
    config = []
    expecting_regex = True
    regex = None
    command = None
    for line in fileinput.input(filename):
        # skip empty lines
        if re.search(r'^\s*$', line):
            continue
        # skip lines that begin with a '#' character
        if re.search('^#', line):
            continue
        # chomp off trailing newline
        if line[-1] == '\n':
            line = line[:-1]
        # the first line in each pair is interpreted as a regular expression
        # note that case is ignored. it would be nice if there was an easy way
        # for the user to choose whether or not case should be ignored.
        if expecting_regex:
            regex = re.compile(line)
            expecting_regex = False
        # the second line in each pair is interpreted as a command
        else:
            command = string.split(line)
            config.append((regex, command))
            expecting_regex = True
    return config


def strConfig(config):
    """Stringifies a list of moosicd filetype-player associations.
 
    This function converts the list used to store filetype-to-player
    associations to a string. The "config" parameter is the list to be
    converted. The return value is a good-looking string that represents the
    contents of the list of associations.
    """
    s = ''
    for regex, command in config:
        s = s + regex.pattern + '\n\t' + string.join(command) + '\n'
    return s


def getConfigFile(confdir):
    '''A procedure which prepares the moosicd configuration file.
    
    The name of the configuration file is returned. The "confdir" parameter is
    the name of the configuration directory. The configuration directory and
    configuration file will be created if they don't already exist.
    '''
    conffile = os.path.join(confdir, 'config')
    if not os.path.exists(confdir):
        try:
            os.makedirs(confdir, 0700)
        except IOError, e:
            sys.exit('Error creating directory "%s": %s' % (confdir, e.strerror))
    if not os.path.exists(conffile):
        try:
            f = open(conffile, 'w')
            f.write('''\
# %s
# This file associates filetypes with commands which play them.
#
# The format of this file is as follows:  Every pair of lines forms a unit.
# The first line in a pair is a regular expression that will be matched against
# items in the play list.  The second line in a pair is the command that will
# be used to play any items that match the regular expression.  The name of the
# item to be played will be appended to the end of this command line.
#
# The command will not be interpreted by a shell, so don't bother trying to use
# shell variables or globbing or I/O redirection, and be mindful of how you use
# quotes and parentheses.  If you need any of these fancy features, wrap up the
# command in a real shell script (and remember to use an "exec" statement to
# invoke the program that does the actual song playing, otherwise Moosic won't
# be able to do things like stop or pause the song).
#
# Blank lines and lines starting with a '#' character are ignored.  Regular
# expressions specified earlier in this file take precedence over those
# specified later.
 
(?i)\.mp3$
mpg123 -q
 
(?i)\.midi?$
timidity -idq
 
(?i)\.(mod|xm|s3m|stm|it|mtm|669|amf)$
mikmod -q
 
(?i)\.(wav|8svx|aiff|aifc|aif|au|cdr|maud|sf|snd|voc)$
sox $item -t ossdsp /dev/dsp
 
(?i)\.ogg$
ogg123 -q
 
(?i)\.m3u$
moosic -o pl-add
 
(?i)^cda://(\S+)
takcd \1''' % conffile)
            f.close()
        except IOError, e:
            sys.exit('Error creating configuration file "%s": %s' % (conffile, e))
    if not os.path.isfile(conffile):
        sys.exit('Error: "%s" exists, but is not a regular file.\n'
            "I can't run without a proper configuration file." % (conffile))
    return conffile


def split_range(range):
    '''A helper function that handles the ranges used by several Moosic methods.
    '''
    if len(range) == 0:
        start, end = 0, len(data.song_queue)
    elif len(range) == 1:
        start, end = range[0], len(data.song_queue)
    elif len(range) == 2:
        start, end = range[0], range[1]
    else:
        raise TypeError("Invalid range argument: %s" % range)
    return start, end



class Log:
    """A very simple logging facility.

    All messages logged with this facility have a priority associated with them.
    The valid priorities are defined by the following class constants (listed in
    order of increasing priority): DEBUG, NOTICE, WARNING, and ERROR. The
    "priorityNames" dictionary is meant for mapping these constants into strings
    that contain their respective names, and should not be modified.
    """
    # The following class attributes are constants used to specify the priority
    # of a log message.
    DEBUG = 3
    NOTICE = 2
    WARNING = 1
    ERROR = 0

    priorityNames = {
        DEBUG:"DEBUG", NOTICE:"NOTICE", WARNING:"WARNING", ERROR:"ERROR"
    }

    def __init__(self, file, loglevel=WARNING):
        """Creates a Log object.
        
        "file" is the file-like object to which log messages will be written.
        
        "loglevel" is the minimum priority level needed for a message to be
        logged. Messages with a priority lower than this will be ignored.  One
        of the constants defined in this class (i.e. DEBUG, NOTICE, WARNING, or
        ERROR) should be used as the value of this parameter.
        """
        if not hasattr(file, 'write') or not callable(file.write):
            raise TypeError("argument 1: expected a file object")
        self.logfile = file
        self.loglevel = loglevel

    def __call__(self, priority, message):
        """Sends a message to be logged by the Log object.
        
        "priority" is a measure of the message's urgency. One of the constants
        defined in this class (i.e. DEBUG, NOTICE, WARNING, or ERROR) should be
        used as the value of this parameter. If the priority of the message is
        lower than the threshold associated with the Log object, then the
        message will not be logged.
        
        "message" is a string that contains the text of the message.
        
        The return value is the object passed as the "message" parameter.
        """
        orig_message = message
        if priority <= self.loglevel:
            # Portability note: Unix-style newlines are assumed.
            message = string.replace(message, "\n", "\n\t")
            now = time.strftime('%I:%M:%S%p', time.localtime(time.time()))
            message = "%s [%s] %s\n" % (now, self.priorityNames[priority], message)
            self.logfile.write(message)
        return orig_message


class UnixMoosicRequestHandler(SimpleXMLRPCServer.SimpleXMLRPCRequestHandler):
    """An adaptation of SimpleXMLRPCRequestHandler for use with Unix sockets.
    """
    # The Nagle algorithm issue doesn't apply to non-TCP sockets.
    disable_nagle_algorithm = False

    def address_string(self):
        """Returns the client address in a format appropriate for logging.
        
        BaseHTTPServer.BaseHTTPRequestHandler (which is a base class of
        SimpleXMLRPCServer.SimpleXMLRPCRequestHandler) assumes that its
        client_address attribute is a (host, port) tuple, which is a false
        assumption if we are using a socket that doesn't use the INET address
        family.  So, this method has been overridden.
        """
        return self.client_address


class TcpMoosicRequestHandler(SimpleXMLRPCServer.SimpleXMLRPCRequestHandler):
    """An adaptation of SimpleXMLRPCRequestHandler for use with TCP sockets.
    """
    # Actually, no adaptation needs to be done.
    pass


class UnixMoosicServer(SocketServer.UnixStreamServer,
                       SimpleXMLRPCServer.SimpleXMLRPCServer):
    """A server that responds to Moosic requests via a Unix (local) socket.
    """
    # Portability note: By default, Unix domain sockets are used to implement
    # interprocess communication between the client and the server. This prevents
    # this program from working on (most, if not all) non-Unix systems.
    def __init__(self, addr, logRequests=False):
        SimpleXMLRPCServer.SimpleXMLRPCServer.__init__(self, addr,
                requestHandler=UnixMoosicRequestHandler,
                logRequests=logRequests)

    def handle_error(self, request, client_address):
        """Handle an error gracefully."""    
        log_exception(request, client_address)


class TcpMoosicServer(SimpleXMLRPCServer.SimpleXMLRPCServer):
    """A server that responds to Moosic requests via TCP/IP.
    """
    def __init__(self, addr, logRequests=False):
        SimpleXMLRPCServer.SimpleXMLRPCServer.__init__(self, addr,
                requestHandler=TcpMoosicRequestHandler,
                logRequests=logRequests)

    def handle_error(self, request, client_address):
        """Handle an error gracefully."""    
        log_exception(request, client_address)


class ThreadedUnixMoosicServer(SocketServer.ThreadingMixIn,
                       SocketServer.UnixStreamServer,
                       SimpleXMLRPCServer.SimpleXMLRPCServer):
    """A server that responds to Moosic requests via a Unix (local) socket.
    """
    # Portability note: By default, Unix domain sockets are used to implement
    # interprocess communication between the client and the server. This prevents
    # this program from working on (most, if not all) non-Unix systems.
    def __init__(self, addr, logRequests=False):
        SimpleXMLRPCServer.SimpleXMLRPCServer.__init__(self, addr,
                requestHandler=UnixMoosicRequestHandler,
                logRequests=logRequests)

    def process_request(self, request, client_address):
        """Start a new thread to process the request.
        
        The new thread is specifically set as a non-daemon thread to ensure that
        the request is properly completed, even if the rest of the server is
        shutting down.
        """
        # Apparently, some platforms (such as various forms of BSD) won't start
        # a new thread until the previous thread has performed a blocking
        # operation (such as a trivial call to sleep()):
        # <http://groups.google.com/groups?q=threading.thread+block+bsd&hl=en&lr=&ie=UTF-8&oe=utf-8&selm=mailman.1061812864.3431.clpa-moderators%40python.org&rnum=1>
        # [scroll down to: "None of my threads seem to run: why?"]
        time.sleep(0.001)

        t = threading.Thread(target=self.process_request_thread,
                             args=(request, client_address))
        t.setDaemon(False)
        t.start()

    def handle_error(self, request, client_address):
        """Handle an error gracefully."""    
        log_exception(request, client_address)


class ThreadedTcpMoosicServer(SocketServer.ThreadingMixIn,
                      SimpleXMLRPCServer.SimpleXMLRPCServer):
    """A server that responds to Moosic requests via TCP/IP.
    """
    def __init__(self, addr, logRequests=False):
        SimpleXMLRPCServer.SimpleXMLRPCServer.__init__(self, addr,
                requestHandler=TcpMoosicRequestHandler,
                logRequests=logRequests)

    def process_request(self, request, client_address):
        """Start a new thread to process the request.
        
        The new thread is specifically set as a non-daemon thread to ensure that
        the request is properly completed, even if the rest of the server is
        shutting down.
        """
        # A trivial call to sleep() is made here for the same reason as it is
        # done in the analogous method of UnixMoosicServer.
        time.sleep(0.001)

        t = threading.Thread(target=self.process_request_thread,
                             args=(request, client_address))
        t.setDaemon(False)
        t.start()

    def handle_error(self, request, client_address):
        """Handle an error gracefully."""    
        log_exception(request, client_address)

def log_exception(request, client_address):
    """Makes note of an exception in the error log.

    This logs a traceback of the error (with "ERROR" priority) and
    continues.
    """    
    exception = sys.exc_info()[1]
    # Ignore "broken pipe" errors.
    if isinstance(exception, IOError) and exception[0] == errno.EPIPE:
        return
    data.log(Log.ERROR,
        '-'*40 + '\n' + \
        'Exception happened during processing of request from ' + \
        str(client_address) + '\n' + \
        ''.join(traceback.format_exception(*sys.exc_info())) + \
        '-'*40
    )

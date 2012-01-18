# moosic/server/main.py - the server portion of the Moosic jukebox system.
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

import sys, os, os.path, string, time, threading, re
import socket, signal, atexit
import cPickle as pickle
from moosic import VERSION
from moosic.server.daemonize import daemonize

# Define the True and False constants if they don't already exist.
try: True
except NameError: True = 1
try: False
except NameError: False = 0

#----- The Primary Components of moosicd -----#
# moosicd consists of several interacting components: the request handler, the
# queue consumer, and the song player.  The request handler is in charge of
# listening for requests from a moosic client and reacting accordingly.  The
# queue consumer pops items off of the playlist and plays each of them, one
# after another.  The song player is what the queue consumer uses to play each
# song.

#----- Threads of control -----#
# moosicd is a multi-threaded program, and the two most important threads are
# the ones in which the queue consumer and the request handler run.  The queue
# consumer is run in the program's "main" thread, while the request handler is
# run in a "daemon" thread that quits as soon as the main thread quits.
#
# The song player also represents a separate subprocess, since it forks off to
# spawn a player program, but this runs in series with the queue consumer and
# blocks until its child returns, so it is considered part of the queue
# consumer's thread.
#
# Finally, each time the request handler receives a request, it creates a new
# thread to execute the request so that multiple requests can be processed
# simultaneously.  In practice, however, multiple requests are usually not
# really executing at the same time for two reasons: 1) request execution is
# normally completed in a very short amount of time, 2) requests which modify
# the state of the Moosic server must use locking to make other non-read-only
# requests wait before executing, so that data consistency is ensured.  These
# threads are are specifically set to have non-daemon status so that they can
# properly return a response to the client even if the other threads have
# terminated.

#---------- the request handler ----------#
# The logic for actually handling specific requests is implemented by the
# moosicd_methods object, which is initialized in the moosic.server.methods
# module.  The rest of the request handler is implemented by classes in the
# moosic.server.support module, UnixMoosicServer and TcpMoosicServer, which are
# minor adaptations of classes from the Python standard library.
from moosic.server.methods import moosicd_methods
from moosic.server.support import *

def request_handler(server):
    try:
        server.serve_forever()
    except socket.error, e:
        data.quitFlag = True  # Tell the queue consumer to quit.
        import errno
        if e[0] == errno.EINTR:
            sys.exit() # Ignore "Interrupted system call" exceptions.
        else:
            sys.exit(data.log(Log.ERROR, 'Socket error: %s' % e))


#---------- the song player ----------#
def play(config, songname):
    """Plays a single music file, and returns when it's over.
    """
    # Match the songname against the regexps in our filetype association table.
    command = None
    for regex, cmd in config:
        match = regex.search(songname)
        if match:
            command = cmd[:]
            break
    if not command:
        data.log(Log.NOTICE, 'No player could be found for "%s".' % songname)
        data.ignore_song_finish = True
        return
    did_replacement = False
    for i in range(len(command)):
        # Replace occurrences of "$item" in the command list.
        replaced = re.sub(r'\$item', songname, command[i])
        if command[i] != replaced:
            command[i] = replaced
            did_replacement = True
        # Replace references to match groups in the command list.
        replaced = match.expand(command[i])
        if command[i] != replaced:
            command[i] = replaced
            did_replacement = True
    if not did_replacement:
        command.append(songname)
    # I forget why I'm flushing stdout here, but it can't hurt. Can it?
    sys.stdout.flush()
    # Classic fork & exec to spawn the external player.
    # Portability note: os.fork() is only available on Unix systems.
    data.player_pid = os.fork()
    if data.player_pid == 0:
        # We don't want the program to grab input.
        fd = os.open('/dev/null', os.O_RDONLY)
        os.dup2(fd, sys.__stdin__.fileno())
        os.close(fd)
        # Open up a file for logging the command's output.
        try:
            logfilename = os.path.join(data.confdir, 'player_log')
            if os.path.exists(logfilename):
                buffering = 1  # Use line-buffered output.
                logfile = open(logfilename, 'a', buffering)
            else:
                buffering = 1  # Use line-buffered output.
                logfile = open(logfilename, 'w', buffering)
            # Delimit each entry in the log file with a time-stamped message.
            now = time.strftime('%I:%M:%S%p', time.localtime(time.time()))
            logfile.write('%s Executing "%s"\n' % (now, string.join(command)))
            logfile.flush()
            # Capture the program's standard error stream.
            os.dup2(logfile.fileno(), sys.__stderr__.fileno())
            # Capture the program's standard output stream.
            os.dup2(logfile.fileno(), sys.__stdout__.fileno())
        except IOError, e:
            data.log(Log.ERROR,
              'Cannot open player log file "%s": %s' % (e.songname, e.strerror))
        # Execute the command.
        try:
            os.execvp(command[0], command)
        except StandardError, e:
            print 'Could not execute "%s": %s' % (' '.join(command), e)
    else:
        os.waitpid(data.player_pid, 0)
        data.player_pid = None


#---------- the queue consumer ----------#
def queue_consumer():
    """The Moosic queue consumer.
    
    This procedure is a simple indefinite loop which is responsible for
    consuming the items in moosicd's queue.
    """
    from moosic.server.methods import current_time
    while not data.quitFlag:
        if data.song_queue and data.qrunning:
            data.lock.acquire()
            try:
                # Pop a song off of the playlist.
                data.current_song = data.song_queue.pop(0)
                # Update internal state variables.
                data.last_queue_update = time.time()
                data.song_start_event = time.time()
                data.current_paused_time = 0
            finally:
                data.lock.release()

            # Play the song.
            data.log(Log.NOTICE, 'Started playing ' + data.current_song)
            play(data.config, data.current_song)
            # Note that control does not return to this point until the
            # song is finished playing.
            data.log(Log.NOTICE, 'Finished playing ' + data.current_song +
                    ' (total playing time: %s)' %
                    time.strftime('%H:%M:%S', time.gmtime(current_time())))

            data.lock.acquire()
            try:
                if data.ignore_song_finish:
                    # Handle the song that just finished playing specially by
                    # skipping certain actions.
                    data.ignore_song_finish = False # Reset the flag now that
                                                    # the special handling has
                                                    # been done.
                else:
                    # Return the song to the end of the queue if loop mode is on.
                    if data.loop_mode:
                        data.song_queue.append(data.current_song)
                        data.last_queue_update = time.time()
                    # Update the history to reflect the fact that the song was
                    # played.
                    data.history.append((data.current_song,
                                         data.song_start_event, time.time()))
                    while len(data.history) > data.max_hist_size:
                        data.history.pop(0)
                # Reset current_song to indicate that nothing is being played.
                if not data.quitFlag:  # (unless moosicd is shutting down)
                    data.current_song = ''
            finally:
                data.lock.release()
        else:
            time.sleep(0.05)


def handleOptions(argv, defaultOpts):
    '''This function interprets the command-line options passed to moosicd.'''
    import getopt
    opts = defaultOpts.copy()
    try:
        options, arglist = getopt.getopt(argv, 'hvqds:c:St:T:fl', ['help',
                'version', 'quiet', 'debug', 'history-size=', 'config=',
                'stdout', 'tcp=', 'tcp-also=', 'foreground', 'local-only'])
    except getopt.GetoptError, e:
        sys.exit('Option processing error: %s' % e)
    for opt, val in options:
        if opt == '-h' or opt == '--help':
            print 'usage:', os.path.basename(argv[0]), '[options]' + '''
    Options:
        -s, --history-size <num> Sets the maximum size of the history list.
                                 (Default: 50)
        -c, --config <dir>  Specifies the directory where moosicd should keep
                            the various files that it uses.
                            (Default: ~/.moosic/)
        -t, --tcp <port>    Listen to the given TCP port number for client
                            requests instead of using the normal communication
                            method.
                            (Beware: this may create network security
                            vulnerabilities.)
        -T, --tcp-also <port> Listen to the given TCP port number for client
                            requests in addition to using the normal
                            communication method.
                            (Beware: this may create network security
                            vulnerabilities.)
        -l, --local-only    Only listen for TCP connections that originate from
                            the local computer.  This only has an effect when
                            --tcp or --tcp-also is used.
        -f, --foreground    Stay in the foreground instead of detaching from the
                            current terminal and going into the background.
        -q, --quiet         Don't print any informational messages.
        -d, --debug         Print additional informational messages.
        -S, --stdout        Output messages to stdout instead of logging to a
                            file. This also prevents the program from putting
                            itself in the background and detaching from the
                            current terminal.
        -v, --version       Print version information and exit.
        -h, --help          Print this help text and exit.'''
            sys.exit(0)
        if opt == '-v' or opt == '--version':
            print "moosicd", VERSION
            print """
Copyright (C) 2001-2003 Daniel Pearson <daniel@nanoo.org>
This is free software; see the source for copying conditions.  There is NO
warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE."""
            sys.exit(0)
        if opt == '-q' or opt == '--quiet':
            opts['verbosity'] = Log.ERROR
        if opt == '-d' or opt == '--debug':
            opts['verbosity'] = Log.DEBUG
        if opt == '-s' or opt == '--history-size':
            try:
                opts['max hist size'] = int(val)
            except ValueError, e:
                print 'Warning: %s. This option has been ignored.' % e
        if opt == '-c' or opt == '--config':
            opts['confdir'] = os.path.abspath(val)
        if opt == '-S' or opt == '--stdout':
            opts['log to stdout'] = True
            opts['daemonize'] = False
        if opt == '-f' or opt == '--foreground':
            opts['daemonize'] = False
        if opt == '-t' or opt == '--tcp':
            try:
                opts['tcp-port'] = int(val)
                opts['ip-socket'] = True
                opts['unix-socket'] = False
            except ValueError, e:
                print 'Warning: %s. This option has been ignored.' % e
        if opt == '-T' or opt == '--tcp-also':
            try:
                opts['tcp-port'] = int(val)
                opts['ip-socket'] = True
                opts['unix-socket'] = True
            except ValueError, e:
                print 'Warning: %s. This option has been ignored.' % e
        if opt == '-l' or opt == '--local-only':
            opts['local-only'] = True
    if arglist:
        print 'Warning: non-option command line arguments are ignored.'
    return opts


#------------ "main" - The program's execution starts here  ------------#
def main(argv):
    # Collect appropriate data from the command-line arguments.
    options = {'log to stdout':False,
               'daemonize':True,
               'unix-socket':True,
               'ip-socket':False,
               'tcp-port':None,
               'local-only':False,
               'verbosity':Log.NOTICE,
               'max hist size':data.max_hist_size,
               'confdir':data.confdir }
    options = handleOptions(argv[1:], options)

    # Read the configuration file, creating it first if it doesn't already
    # exist.  It is important to call getConfigFile() before trying to use
    # confdir as a valid path, since this function creates confdir in the case
    # when it doesn't already exist.
    data.confdir = options['confdir']
    data.conffile = getConfigFile(data.confdir)
    try:
        data.config = readConfig(data.conffile)
    except IOError, e:
        sys.exit('Error reading configuration file "%s": %s' % (data.conffile, e))

    # Initialize the logging system.
    logfilename = os.path.join(data.confdir, 'server_log')
    try:
        if options['log to stdout']:
            logfile = sys.stdout
        elif os.path.exists(logfilename):
            buffering = 1  # Use line-buffered output.
            logfile = open(logfilename, 'a', buffering)
        else:
            buffering = 1  # Use line-buffered output.
            logfile = open(logfilename, 'w', buffering)
    except IOError, e:
        sys.exit('Cannot open server log file "%s": %s' % (logfilename, e.strerror))
    data.log = Log(logfile, options['verbosity'])
    data.log(Log.NOTICE, "Starting up.")

    # Load previously saved state data, if any.
    savefilename = os.path.join(data.confdir, 'saved_state')
    if os.path.exists(savefilename):
        try:
            data.setstate(pickle.load(open(savefilename)))
        except IOError, e:
            data.log(Log.WARNING,
              'Cannot open saved-state file "%s": %s' % (e.filename,e.strerror))
        except pickle.PickleError, e:
            data.log(Log.WARNING,
              'Unpickling error: %s\nCannot load saved state.' % (e))
        except:
            data.log(Log.WARNING,
              'Saved-state file "%s" could not be loaded.' % (savefilename))

    # Allow the max_hist_size specified in the command-line options to override
    # the value from the saved state.
    data.max_hist_size = options['max hist size']

    # Create an instance of the server for listening on a Unix socket.
    if options['unix-socket']:
        server_addr = os.path.join(data.confdir, 'socket')
        try:
            data.moosic_server = UnixMoosicServer(server_addr)
        except socket.error, e:
            import errno
            if e[0] == errno.EADDRINUSE:
                try:
                    import moosic.client.factory
                    moosic.client.factory.LocalMoosicProxy(server_addr).no_op()
                    # If the above hasn't thrown an exception, then there
                    # really is a Moosic server using this socket address.
                    sys.exit(data.log(Log.ERROR,
                        "Error: Tried to start a new moosicd, but an instance "
                        "of moosicd is already running."))
                except socket.error, e:
                    # The socket file at our desired address exists, but it
                    # isn't actually being used by a Moosic server, so we'll
                    # assume that this socket file is stale and remove it.
                    data.log(Log.WARNING, 
                            'Cleaning up stale socket file: "%s".'%server_addr)
                    os.remove(server_addr)
                    # Try to instantiate UnixMoosicServer again.
                    try:
                        data.moosic_server = UnixMoosicServer(server_addr)
                    except socket.error, e:
                        # If we still get an error, it's time to give up. We've
                        # done the best we can do.
                        sys.exit(data.log(Log.ERROR,
                                'Socket error: %s: %s' % (server_addr, e)))
            else:
                sys.exit(data.log(Log.ERROR,
                        'Socket error: %s: %s' % (server_addr, e)))

    # Create an instance of the server for listening on an IP socket.
    if options['ip-socket']:
        if options['local-only']:
            server_addr = ('127.0.0.1', options['tcp-port'])
        else:
            server_addr = ('', options['tcp-port'])
        try:
            data.extra_moosic_server = TcpMoosicServer(server_addr)
        except socket.error, e:
            import errno
            if e[0] == errno.EADDRINUSE:
                try:
                    import moosic.client.factory
                    moosic.client.factory.InetMoosicProxy(*server_addr).no_op()
                    # If the above hasn't thrown an exception, then there
                    # really is a server using this socket address.
                    sys.exit(data.log(Log.ERROR, "A server is already running "
                        "on port %d" % options['tcp-port']))
                except socket.error, e:
                    sys.exit(data.log(Log.ERROR,
                        "localhost:%d is somehow in use already, but I cannot "
                        "contact a server at that address." % options['tcp-port']))
            else:
                sys.exit(data.log(Log.ERROR,
                    'Socket error: localhost %s: %s' % (options['tcp-port'], e)))

    # Deal with the case where there's no server listening on an IP socket.
    if not data.extra_moosic_server:
        data.extra_moosic_server = data.moosic_server
    # Deal with the case where there's no server listening on a Unix socket.
    if not data.moosic_server:
        data.moosic_server = data.extra_moosic_server

    # Install the methods that handle requests into the server.
    data.moosic_server.register_instance(moosicd_methods)
    data.extra_moosic_server.register_instance(moosicd_methods)

    # Daemonize (go into the background, detach from the terminal, etc.).
    if options['daemonize']:
        daemonize(stderr=logfilename)
        data.log(Log.NOTICE, "Transformed into a daemon with PID: %d" % (os.getpid()))

    # Set up a timer to automatically save state at regular intervals.
    def savestate():
        "Save the Moosic server's current state to disk."
        try:
            savefilename = os.path.join(data.confdir, 'saved_state')
            pickle.dump(data.getstate(), open(savefilename, 'w'))
        except IOError, e:
            data.log(Log.WARNING,
              'Cannot open saved-state file "%s" for writing: %s' %
              (e.filename, e.strerror))
        except PicklingError, e:
            data.log(Log.WARNING,
              'Pickling error: %s\nCannot save state.' % (e))

    def save_timer(prev_update):
        if data.last_queue_update != prev_update: # Don't bother waking up the
            savestate()                           # hard disk if nothing has
                                                  # changed.
        t = threading.Timer(300, save_timer, args=(data.last_queue_update,))
        t.setDaemon(True)
        t.start()
    save_timer(0)

    # Set up the signal handlers and exit handler.
    def reconfig(signum=None, stackframe=None):
        from moosic.server.methods import reconfigure
        reconfigure()
    signal.signal(signal.SIGHUP, reconfig)

    def quit(signum=None, stackframe=None):
       #if stackframe:                                              # DEBUG
       #    import traceback                                        #
       #    data.log(Log.DEBUG, traceback.format_stack(stackframe)) #
        if signum:
            data.log(Log.NOTICE, "Killed by signal %d (PID: %d)." %
                                 (signum, os.getpid()))
        sys.exit()
    signal.signal(signal.SIGINT, quit)
    signal.signal(signal.SIGTERM, quit)
    signal.signal(signal.SIGUSR1, quit)
    signal.signal(signal.SIGUSR2, quit)

    def cleanup():
        '''This function is called to perform any cleanup which needs to be done
        when moosicd shuts down.
        '''
        data.log(Log.NOTICE, "Shutting down (PID: %d)." % (os.getpid()))
        # Don't accept any more requests.
        try:
            data.moosic_server.server_close()
            data.extra_moosic_server.server_close()
        except: pass
        # Don't leave unused socket files around.
        if isinstance(data.moosic_server, UnixMoosicServer):
            try: os.remove(data.moosic_server.server_address)
            except: pass
        # Save our current state to disk.
        savestate()
        # Kill the song player.
        if data.current_song:
            try: os.kill(data.player_pid, signal.SIGTERM)
            except: pass
    atexit.register(cleanup)

    # Run the request handler in a separate thread.
    t = threading.Thread(target=request_handler, args=(data.moosic_server,))
    t.setDaemon(True)
    t.start()

    # Start a second request handler if we are serving requests from two
    # different transport methods.
    if data.extra_moosic_server is not data.moosic_server:
        t = threading.Thread(target=request_handler,
                             args=(data.extra_moosic_server,))
        t.setDaemon(True)
        t.start()

    # Run the queue consumer.
    queue_consumer()

if __name__ == '__main__':
    main(sys.argv)

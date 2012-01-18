# moosic/client/cli/main.py - The client portion of the moosic jukebox system.
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

import sys, socket, os, os.path, getopt, xmlrpclib, errno, time, locale, re

from moosic import VERSION
from moosic.utilities import *
from moosic.client.factory import *
from moosic.client.cli.dispatcher import *

# Define the True and False constants if they don't already exist.
try: True
except NameError: True = 1
try: False
except NameError: False = 0

# Giving stderr a shorter name is convenient when printing error messages.
err = sys.stderr

# Set the locale to the user's default settings, if possible.
try: locale.setlocale(locale.LC_ALL, '')
except: pass


def main(argv):
    COMMANDS = get_command_docs() \
        + center_text('This Moosic has Super Cow Powers.', pad_char=' ')
    USAGE = "usage: " + os.path.basename(argv[0]) + \
        " [options] <command>" + '''
    Options:
        -d, --shuffle-dir       When a directory is named on the command line,
                                shuffle the result of recursing through the
                                directory before inserting it into the list.
        -a, --shuffle-args      Shuffle only the arguments explicitly specified
                                on the command line.
        -g, --shuffle-global    Shuffle the entire argument list after
                                directory arguments specified on the command
                                line have been replaced with their contents.
                                This is the default behavior.
        -o, --inorder           Don't shuffle the given filelist at all, and
                                maintain the order specified on the command
                                line.
        -s, --sort              Sort the filelist, regardless of the order
                                specified on the command line.
        -i, --ignore-case       Treat any given regular expressions as if they
                                were case-insensitive.
        -r, --no-recurse        Don't replace directories named on the command
                                line with their contents.
        -n, --non-file-args     Don't change any names given in a filelist.
                                Useful if your filelist consists of URLs or
                                other objects that aren't local files.
        -f, --auto-find         Replace each string in the given filelist with
                                the results of a "fuzzy" search for music files
                                which match that string. (Beware: this can
                                be slow with large music collections.)
        -F, --auto-grep         Replace each string in the given filelist with
                                the results of a regular-expression search for
                                music files which match that string. (Beware:
                                this can be slow with large music collections.)
        -m, --music-dir <dir>   Specifies the directory to search when using the
                                "auto-find" and "auto-grep" features.
                                (Default: ~/music/)
        -c, --config-dir <dir>  Specifies the directory where moosic should
                                find the files kept by moosicd.
                                (Default: ~/.moosic/)
        -t, --tcp <host>:<port> Communicate with a Moosic server that is
                                listening to the specified TCP/IP port on the
                                specified host.  (Not recommended.)
        -N, --no-startserver    Don't automatically start moosicd if it isn't
                                already running.
        -U, --allow-unplayable  Allow songs that the server doesn't know how to
                                play to be added into the song queue.
        -C, --current-in-list   Show the currently playing song in the "list"
                                and "plainlist" commands.
        -S, --showcommands      Print the list of possible commands and exit.
        -h, --help              Print this help text and exit.
        -v, --version           Print version information and exit.
                       This Moosic has Super Cow Powers.'''

    # Option processing.
    def process_options(arglist, opts):
        opts = opts.copy()
        try:
            opt_spec = { 'd':'shuffle-dir',
                         'a':'shuffle-args',
                         'g':'shuffle-global',
                         'o':'inorder',
                         's':'sort',
                         'i':'ignore-case',
                         'r':'no-recurse',
                         'n':'non-file-args',
                         '':'no-file-munge',
                         'f':'auto-find',
                         'F':'auto-grep',
                         'm:':'music-dir=',
                         'c:':'config-dir=',
                         't:':'tcp=',
                         'N':'no-startserver',
                         'U':'allow-unplayable',
                         'C':'current-in-list',
                         'S':'showcommands',
                         'h':'help',
                         'v':'version', }
            short_opts = ''.join(opt_spec.keys())
            long_opts = opt_spec.values()
            options, arglist = getopt.getopt(arglist, short_opts, long_opts)
        except getopt.error, e:
            sys.exit('Option processing error: %s' % e)
        for option, val in options:
            if option == '-d' or option == '--shuffle-dir':
                opts['shuffle-dir'] = True
                opts['shuffle-global'] = False
            if option == '-a' or option == '--shuffle-args':
                opts['shuffle-args'] = True
                opts['shuffle-global'] = False
            if option == '-g' or option == '--shuffle-global':
                opts['shuffle-global'] = True
            if option == '-o' or option == '--inorder':
                opts['shuffle-global'] = False
                opts['shuffle-args'] = False
                opts['shuffle-dir'] = False
            if option == '-s' or option == '--sort':
                opts['shuffle-global'] = False
                opts['shuffle-args'] = False
                opts['shuffle-dir'] = False
                opts['sort'] = True
            if option == '-i' or option == '--ignore-case':
                opts['ignore-case'] = True
            if option == '-r' or option == '--no-recurse':
                opts['dir-recurse'] = False
            if option == '-n' or option == '--no-file-munge' or option == '--non-file-args':
                opts['file-munge'] = False
                opts['dir-recurse'] = False
            if option == '-f' or option == '--auto-find':
                opts['auto-find'] = True
                opts['auto-grep'] = False
            if option == '-F' or option == '--auto-grep':
                opts['auto-grep'] = True
                opts['auto-find'] = False
            if option == '-m' or option == '--music-dir':
                opts['music-dir'] = os.path.abspath(os.path.expanduser(val))
            if option == '-c' or option == '--config-dir':
                opts['config-dir'] = os.path.abspath(os.path.expanduser(val))
            if option == '-t' or option == '--tcp':
                if ":" not in val:
                    sys.exit(('Invalid address: %s\n' % val) +
                         'You must specify both a hostname and a port number.\n'
                         'For example, "example.com:123"')
                host, port = val.split(':', 1)
                try:
                    port = int(port)
                except ValueError, e:
                    sys.exit("Invalid port number: %s" % port)
                opts['tcp-address'] = (host, port)
            if option == '-N' or option == '--no-startserver':
                opts['start moosicd'] = False
            if option == '-U' or option == '--allow-unplayable':
                opts['no-unplayables'] = False
            if option == '-C' or option == '--current-in-list':
                opts['current-in-list'] = True
            if option == '-S' or option == '--showcommands':
                print COMMANDS
                sys.exit(0)
            if option == '-h' or option == '--help':
                print USAGE
                sys.exit(0)
            if option == '-v' or option == '--version':
                print "moosic", VERSION
                print """
Copyright (C) 2001-2003 Daniel Pearson <daniel@nanoo.org>
This is free software; see the source for copying conditions.  There is NO
warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE."""
                sys.exit(0)
        return arglist, opts

    home = os.getenv('HOME', '/tmp')
    # Set the built-in default options.
    opts = {'shuffle-global':True, 'shuffle-args':False, 'shuffle-dir':False,
            'debug':False, 'file-munge':True, 'sort':False, 'dir-recurse':True,
            'config-dir':os.path.join(home, '.moosic', ''), 'tcp-address':None,
            'music-dir':os.path.join(home, 'music', ''), 'auto-find':False,
            'auto-grep':False, 'start moosicd':True, 'ignore-case':False,
            'sort':False, 'rc-filename':os.path.join(home, '.moosicrc'),
            'no-unplayables':True, 'current-in-list':False}
    # Gather options specified before the command.
    arglist, opts = process_options(argv[1:], opts)
    # Pluck the command out of the argument list.
    if not arglist:
        sys.exit("You must provide a command.\n"
         "Use the --showcommands option to learn what commands are available.\n"
         "Use the --help option to learn what options are available.\n"
         "usage: %s [options] <command>" % os.path.basename(argv[0]))
    command = arglist.pop(0)
    command = command.lower()
    command = re.sub(r'[\W_]', r'', command)
    # Gather options specified after the command.
    if command != 'startserver':  # ...except for the startserver command.
        arglist, opts = process_options(arglist, opts)
    # TODO: Gather option values from a config file.
    #file_opts = process_configfile(opts['rc-filename'], opts)
    # Use the options from the command-line to override the options from the
    # config file.
    #file_opts.update(opts)
    #opts = file_opts

    if command not in dispatcher:
        sys.exit(wrap(('Error: invalid command: "%s"\n' % command) +
            "Use the --showcommands option or the 'help' command to see the "
            "available commands. Use the --help option to learn about the "
            "possible options.\n"
            "usage: %s [options] <command>" % os.path.basename(argv[0]), 79))

    # Check the number of arguments given to the command.
    if not check_args(command, arglist):
        sys.exit(2)

    # Create a proxy object for speaking to the Moosic server.
    if opts['tcp-address']:
        host, port = opts['tcp-address']
        moosic = InetMoosicProxy(host, port)
    else:
        server_address = os.path.join(opts['config-dir'], 'socket')
        moosic = LocalMoosicProxy(server_address)

    # Make sure that our connection to the server is working properly.
    try:
        if command != 'startserver': # unless the user is starting it explicitly
            moosic.no_op()
    except socket.error, e:
        if e[0] in (errno.ECONNREFUSED, errno.ENOENT):
            # The server doesn't seem to be running, so let's try to start it
            # for ourselves.
            if opts['tcp-address']:
                failure_reason = "The target Moosic server is on a remote computer."
            elif opts['start moosicd']:
                print >>err, "Notice: The Moosic server isn't running, so it " \
                             "is being started automatically."
                failure_reason = startServer('moosicd', '-c', opts['config-dir'])
            else:
                failure_reason = "Automatic launching of the server is disabled."
            if failure_reason:
                sys.exit(wrap("Error: The server (moosicd) doesn't seem to be "
                         "running, and it could not be started automatically "
                         "because:\n" + failure_reason, 79))
            else:
                # Wait bit to give moosicd time to start up.
                time.sleep(0.25)
                # Test the server connection again.
                try:
                    moosic.no_op()
                except Exception, e:
                    # We tried our best. Finally give up.
                    sys.exit("An attempt was made to start the Moosic "
                             "server, but it still can't be contacted.\n"
                             "%s: %s" % (str(e.__class__).split('.')[-1], e))
        else:
            sys.exit("Socket error: %s" % e)

    try:
        # Dispatch the command.
        exit_status = dispatcher[command](moosic, arglist, opts)
    except socket.error, e:
        exit_status = "Socket error: %s" % e[1]
    except xmlrpclib.Fault, e:
        if ':' in e.faultString:
            fault_type, fault_msg = e.faultString.split(':', 1)
            fault_type = fault_type.split('.')[-1]
            exit_status = "Error from Moosic server: [%s] %s" % (fault_type, fault_msg)
        else:
            exit_status = "Error from Moosic server: %s" % e.faultString
    except xmlrpclib.ProtocolError, e:
        exit_status = "RPC protocol error: %s %s." % (e.errcode, e.errmsg)
    except ValueError, e:
        exit_status = "Error: %s" % e
    except Exception, e:
        if isinstance(e, SystemExit):
            raise e
        else:
            exit_status = "%s: %s" % (str(e.__class__).split('.')[-1], e)
    sys.exit(exit_status)


if __name__ == '__main__':
    main(sys.argv)

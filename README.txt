Moosic - A musical jukebox program.
Version 1.5.6
By Daniel Pearson

Moosic is a music player that focuses on convenient and powerful playlist
management.  It consists of a server process that maintains a queue of music
files to play and a client program which sends commands to the server.  The
server continually runs through its playlist, popping items off the top of the
list and playing each with an external program.  The standard client is a simple
command-line utility which allows you to perform powerful operations upon the
server's queue, including the addition of whole directory trees, automatic
shuffling, and item removal according to regular expressions.  The server comes
configured to play MP3, Ogg, MIDI, MOD, and WAV files.

REQUIREMENTS:
The primary requirement is a Python interpreter that supports version 2.2 of the
language (or later) and also includes support for threads.  It also relies on
the Unix "find" utility.  It relies upon external programs for actually playing
the music files.  The default setup uses mpg123 for MP3, timidity for MIDI,
ogg123 for Ogg/Vorbis, mikmod for the whole range of MOD formats, TakCD for
audio CDs, and SOX for a wide variety of sound other (mostly uncompressed) sound
file formats.  Moosic will only work on Unix systems, since it uses a wide
variety of Unix-only features.  All of these portability issues are noted within
the source code.

INSTALLATION:
After extracting the archive file (tarball) used to distribute Moosic, change to
the directory that contains Moosic, and run "python setup.py install" in a
terminal window with the privileges of root (the system administration account).

If you are using the Python installation that is included with Mac OS X, then
you should add the "--install-scripts" option to the installation command to
choose to install the executable portions of Moosic into a directory that is
listed in your PATH environment variable.  For instance, "python setyp.py
install --install-scripts /usr/bin".

If you cannot or do not want to install Moosic with root privileges, you can
install it into your own home directory by running "python setup.py install
--home=~" instead.  If you install Moosic into your home directory, make sure
that the PYTHONPATH environment variable is set and includes the directory
~/lib/python/.  Also make sure that your PATH environment variable includes the
~/bin/ directory.

USAGE:
"moosic" is the command-line program that provides the main interface to the
Moosic jukebox.  It works by sending a command to the Moosic server and
returning the response, if any.  The first non-option argument given to moosic
is the name of the command to be performed.  Use "moosic --showcommands" to get
a list of all the different possible commands, or read moosic's manual page.
There are very many commands, so you should start by just learning a few
commonly used commands, and only learning others as you feel the need.  I
recommend starting with the following short command vocabulary: add, list, stop,
play, and shuffle.

For example, "moosic add foo.mp3" adds the file foo.mp3 (in the current
directory) to the end of the song queue and returns you immediately back to your
shell prompt without printing any output (unless an error occurs).  Compare with
"moosic list", which will list the contents of the song queue.  Note that if the
song queue is empty, "moosic list" will not display anything.

Any command which takes a list of files as an argument will also accept
directories, and doing so will cause every file below that directory to be
included in the file-list.  Note that the default behavior of moosic is to
shuffle everything in a file-list before sending the list to the server, but
only after recursively expanding named directories.  You can disable shuffling
by using the -o option.  Use "moosic --help" to learn about all the options for
changing the shuffling behavior, as well as the other command options.

When the Moosic server isn't already running, moosic will automatically start it
for you (unless you specifically request otherwise with a command-line option).
For backwards compatibility, the "moosicd" program can be run to explicitly
start the server.  However, this usage is obsolete because you can run "moosic
startserver" to achieve the same effect.  This means that you can delete the
"moosicd" program from your system if you want.

LEGAL DETAILS:
This is free and unencumbered software released into the public domain.

Anyone is free to copy, modify, publish, use, compile, sell, or
distribute this software, either in source code form or as a compiled
binary, for any purpose, commercial or non-commercial, and by any
means.

In jurisdictions that recognize copyright laws, the author or authors
of this software dedicate any and all copyright interest in the
software to the public domain. We make this dedication for the benefit
of the public at large and to the detriment of our heirs and
successors. We intend this dedication to be an overt act of
relinquishment in perpetuity of all present and future rights to this
software under copyright law.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.

For more information, please refer to <http://unlicense.org/>

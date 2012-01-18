#!/usr/bin/env python

from distutils.core import setup
import sys
import os.path

# Patch distutils if it can't cope with the "classifiers" or
# "download_url" keywords.
if sys.version < '2.2.3':
    from distutils.dist import DistributionMetadata
    DistributionMetadata.classifiers = None
    DistributionMetadata.download_url = None

setup(name = 'moosic',
      version = '1.5.6',
      author = 'Daniel J. Pearson',
      author_email = 'daniel@nanoo.org',
      url = 'http://www.nanoo.org/moosic/',
      #download_url = 'http://www.nanoo.org/moosic/dist/',
      license = 'The Unlicense',
      description = 'A powerful music queue manager.',
      long_description = '''
Moosic is a music player that focuses on easy playlist management. It consists
of a server process that maintains a queue of music files to play and a client
program which sends commands to the server. The server continually runs through
its playlist, popping items off the top of the list and playing each with an
external program. The client is a simple command-line utility which allows you
to perform powerful operations upon the server's queue, including the addition
of whole directory trees, automatic shuffling, and item removal according to
regular expressions. The server comes configured to play MP3, Ogg, MIDI, MOD,
and WAV files.
''',
      classifiers = [
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Environment :: No Input/Output (Daemon)',
        'Intended Audience :: End Users/Desktop',
        'License :: Public Domain',
        'Natural Language :: English',
        'Operating System :: POSIX',
        'Operating System :: Unix',
        'Programming Language :: Python',
        'Topic :: Multimedia :: Sound/Audio :: Players',
        'Topic :: Multimedia :: Sound/Audio :: Players :: MP3',
        ],
      scripts = ['scripts/moosic', 'scripts/moosicd'],
      packages = ['moosic', 'moosic.server', 'moosic.client', 'moosic.client.cli'],
      data_files = [
        ('share/man/man1', ['doc/moosic.1', 'doc/moosicd.1']),
        ('share/man/man3', ['doc/Moosic_API.3']),
        ('share/doc/moosic',
            ['README.txt', 'License.txt', 'ChangeLog', 'NEWS',
            'doc/History.txt', 'doc/Todo', 'doc/Moosic_API.txt',
            'doc/moosic_hackers.txt']),
        ('share/doc/moosic/html',
            ['doc/Moosic_API.html', 'doc/moosic.html', 'doc/moosicd.html']),
        ('share/doc/moosic/examples',
            ['examples/completion', 'examples/server_config']),
        #('/etc/bash_completion.d/', ['examples/completion']),
        ],
)

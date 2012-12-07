#!/usr/bin/python2.4

# Copyright 2008 Google Inc.
# Author : Anoop Chandran <anoopj@google.com>
#
# openduckbill is a simple backup application. It offers support for
# transferring data to a local backup directory, NFS. It also provides
# file system monitoring of directories marked for backup. Please read
# the README file for more details.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""This module takes care of the logging and command line argument parsing.

logger helps in creating a logging system for the application and also
manages to parse command line arguments and set-unset features accordingly.
Logging is initialised by function LoggerInit while GetArgs parse commandline
arguments.
"""

import getopt
import logging
import os
import sys


class LogArgManager:
  """Class provides methods to perform logging and parse command line args."""

  def __init__(self):
    """Set the default logging path and config file path."""

    self.debug = False
    self.logdir = '~/.openduckbill/'
    self.defconfig = os.path.join(self.logdir, 'config.yaml')
    self.logfile = 'messages.log'
    self.myname = 'openduckbill'
    self.filename = os.path.join(self.logdir, self.logfile)
    self.arg_conffile = None

  def Usage(self):
    """Prints usage."""

    print 'Usage : %s -D (Debug)' % (self.myname)
    print '      : %s -F (Run in foreground - No daemon)' % (self.myname)
    print '      : %s -R (Show resource usage (used with -D))' % (self.myname)
    print '      : %s -c <path to config file>' % (self.myname)
    print '      : %s -n (Don\'t perform any backup (dry-run))' % (self.myname)
    print '      : %s -h (Show this message)' % (self.myname)

  def LogInit(self):
    """Calls function LoggerInit to start initialising the logging system."""

    logdir = os.path.normpath(os.path.expanduser(self.logdir))
    self.logfilename = os.path.normpath(os.path.expanduser(self.filename))
    if not os.path.isdir(logdir):
      try:
        os.mkdir(logdir)
      except OSError, e:
        msg = ('%s' % (e))
        print msg
        sys.exit(1)
    self.LoggerInit(self.myname)

  def LoggerInit(self, loggername):
    """Initialise the logging system.

    This includes logging to console and a file. By default, console prints
    messages of level WARN and above and file prints level INFO and above.
    In DEBUG mode (-D command line option) prints messages of level DEBUG
    and above to both console and file.

    Args:
      loggername: String - Name of the application printed along with the log
      message.
    """

    fileformat = '[%(asctime)s] %(name)-10s: %(levelname)-8s: %(message)s'

    self.logger = logging.getLogger(loggername)
    self.logger.setLevel(logging.INFO)

    self.console = logging.StreamHandler()
    self.console.setLevel(logging.WARN)
    consformat = logging.Formatter(fileformat)
    self.console.setFormatter(consformat)

    self.filelog = logging.FileHandler(filename=self.logfilename, mode='a')
    self.filelog.setLevel(logging.INFO)
    self.filelog.setFormatter(consformat)

    self.logger.addHandler(self.filelog)
    self.logger.addHandler(self.console)

  def GetArgs(self):
    """Get command line arguments and configure variables accordingly.

    Options supported are debug mode (-D), Foreground mode (-F), show resource
    usage (-R), rsync dry run (-n), show deleted files (-s), specify
    configuration file (-c).
    """

    self.nofork = False
    self.showresources = False
    self.dryrun = False
    self.deletor_disable = False
    self.internal_disable = False
    self.showdelfiles = False

    try:
      optlist, optarg = getopt.getopt(sys.argv[1:], 'DFRhsnc:')
    except getopt.GetoptError, e:
      self.logger.info(e)
      self.LogStop()
      self.Usage()
      sys.exit(1)
    for opt, arg in optlist:
      if opt == '-h':
        self.LogStop()
        self.Usage()
        sys.exit(1)
      if opt == '-D':
        self.debug = True
        self.console.setLevel(logging.DEBUG)
        self.filelog.setLevel(logging.DEBUG)
        self.logger.setLevel(logging.DEBUG)
        self.logger.debug('==> Enabling Debug mode')
      if opt == '-c':
        self.arg_conffile = arg
      if opt == '-R':
        self.showresources = True
        self.logger.debug('==> Resource usage will be printed')
      if opt == '-n':
        self.dryrun = True
        self.logger.debug('==> Dry run!')
      if opt == '-s':
        self.showdelfiles = True
      if opt == '-F':
        self.nofork = True
        self.logger.debug('==> No Daemon mode selected')
    if not self.nofork:
      self.console.setLevel(logging.WARN)

  def LogStop(self):
    """Shutdown logging process."""

    logging.shutdown()

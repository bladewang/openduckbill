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

"""Helper class, does command execution and returns value.

This class has the method RunCommandPopen which executes commands passed to
it and returns the status.
"""

import os
import subprocess
import sys


class CommandHelper:
  """Run command and return status, either using Popen or call

  """

  def __init__(self, log_handle=''):
    """Initialise logging state

    Logging enabled in debug mode.

    Args:
      log_handle: Object - a handle to the logging subsystem.
    """
    self.logmsg = log_handle
    if self.logmsg.debug:
      self.stdout_debug = None
      self.stderr_debug = None
    else:
      self.stdout_debug = 1
      self.stderr_debug = 1


  def RunCommandPopen(self, runcmd):
    """Uses subprocess.Popen to run the command.

    Also prints the command output if being run in debug mode.

    Args:
      runcmd: List - path to executable and its arguments.

    Retuns:
      runretval: Integer - exit value of the command, after execution.
    """

    stdout_val=self.stdout_debug
    stderr_val=self.stderr_debug

    if stdout_val:
      stdout_l = file(os.devnull, 'w')
    else:
      stdout_l=subprocess.PIPE
    if stderr_val:
      stderr_l = file(os.devnull, 'w')
    else:
      stderr_l=subprocess.STDOUT
    try:
      run_proc = subprocess.Popen(runcmd, bufsize=0,
                                  executable=None, stdin=None,
                                  stdout=stdout_l, stderr=stderr_l)
      if self.logmsg.debug:
       output = run_proc.stdout
       while 1:
         line = output.readline()
         if not line:
           break
         line = line.rstrip()
         self.logmsg.logger.debug("Command output: %s" % line)
      run_proc.wait()
      runretval = run_proc.returncode
    except OSError, e:
      self.logmsg.logger.error('%s', e)
      runretval = 1
    except KeyboardInterrupt, e:
      self.logmsg.logger.error('User interrupt')
      sys.exit(1)
    if stdout_l:
      pass
      #stderr_l.close()
    if stderr_l:
      pass
      #stderr_l.close()
    return runretval

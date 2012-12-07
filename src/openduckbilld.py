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

"""The wrapper which starts the application.

openduckbilld is a wrapper to rest of the application code. The function
StartOpenDuckbill calls the code which reads the config file and does rest of 
the initialisation.
"""

import daemon


def StartOpenDuckbill():
  """Starts the process of setting up environment and initialisation."""

  main_config = 'config.yaml'
  dbinit = daemon.OpenDuckbillMain(main_config)
  if dbinit.MainInitialize():
    dbinit.BackupInitialize()


if __name__ == '__main__':
  StartOpenDuckbill()

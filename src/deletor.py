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

"""Removes old files/directories not longer part of the backup schedule.

This module is responsible for removing any files/directories from
the backup partition, if the file/directory is not more part of an active
backup schedule or is not being backed up anymore (discontinued). This module
is not active when backup method is RSYNC.
"""

import os
import re
import stat
import tempfile
import threading
import time


class EntryDeletor(threading.Thread):
  """This class provides methods to remove files/directories from backup dir."""

  def __init__(self, backup_dir, entry_list, retention_time, loghandle,
               show_files=False):
    """Initialses deletor thread.

    Args:
      backup_dir: String - path of the backup directory
      entry_list: List - List of entries. Each entry is a dictionary.
      retention_time: Integer - Time after which file is considered for removal.
      loghandle: Object - Handle to the logging object.
      show_files: Boolean - Used to tell the module whether or not to log
        removed file/directory info.
    """

    threading.Thread.__init__(self, name='EntryDeletor')
    self.backup_dir = backup_dir
    self.entry_list = entry_list
    self.retention_time = retention_time
    self.loghandle = loghandle
    self.show_files = show_files
    self.fd = None

  def run(self):
    """Starts the deletor thread.

    Finds and deletes all files which are
    not part of backup schedule or has been discontinued and older than
    retention_time (as specified in config file)
    """

    if self.CreateDeleteList():
      self.ComputeDeleteTime()
    else:
      self.loghandle.logger.info('No unscheduled files found in backup drive.')
      self.loghandle.deletor_disable = True
      self.loghandle.internal_disable = True
    os.chdir('/tmp')

  def PrintToFile(self, opr, msg=''):
    """Print message passed to a file (if -s command line option is passed).

    Args:
      opr: String - Kind of operation to be done on a file
        'o' - Open file for writing
        'w' - Write to file
        'c' - Close file
      msg: String - The message to be printed to file.

    Returns:
      False - On error
    """

    if self.show_files:
      if opr == 'o':
        if not self.fd:
          try:
            self.fd, self.fdname = tempfile.mkstemp('.glbdelete', 'tmp-',
                                                    '/tmp/')
            self.loghandle.logger.debug('Deleted entry listed in file %s',
                                        self.fdname)
          except OSError, e:
            self.loghandle.logger.warning('Opening failed; %s', e)
            self.show_files = False
            return
          os.write(self.fd, '\nBEGIN =>' + time.ctime() + '\n')
      if opr == 'w':
        if self.fd:
          try:
            os.write(self.fd, msg)
          except OSError, e:
            self.loghandle.logger.warning('Writing Failed; %s', e)
            return
      if opr == 'c':
        if self.fd:
          try:
            os.write(self.fd, '\nEND =>' + time.ctime() + '\n')
          except OSError, e:
            self.loghandle.logger.warning('Closing Failed; %s', e)
            return

  def CreateDeleteList(self):
    """Function finds each file/directory not part of backup schedules.

    Finds files/directories which are no more part of the backup schedules (not
    listed in entry section of the config file).

    Returns:
      ret_val: Boolean - True if there are files to be removed, else False.
    """

    tmpschedlist = []
    tmpnoschedlist = []
    filelist = []
    try:
      os.chdir(self.backup_dir)
    except OSError, e:
      self.loghandle.logger.info('%s', e)
      self.PrintToFile('c')
      return False
    # Find all file/directories in the backup directories, append them to a
    # list
    try:
      contentlist = os.walk(self.backup_dir)
    except StopIteration:
      self.loghandle.logger.info('Nothing to list here.')
    try:
      toplevel = contentlist.next()
    except StopIteration:
      self.loghandle.logger.info('Nothing to list here.')
    while 1:
      for directory in toplevel[1]:
        filelist.append(re.split(self.backup_dir,
                                 (os.path.join(toplevel[0], directory)))[1])
      for files in toplevel[2]:
        filelist.append(re.split(self.backup_dir,
                                 (os.path.join(toplevel[0], files)))[1])
      try:
        toplevel = contentlist.next()
      except StopIteration:
        break

    # Find all files/directories which are not part of the backup schedule
    for file_item in filelist:
      if file_item:
        for item in self.entry_list:
          if (re.match(item['path'], file_item)
              or re.match(file_item, item['path'])):
            try:
              tmpschedlist.index(file_item)
            except ValueError:
              tmpschedlist.append(file_item)
            try:
              tmpnoschedlist.remove(file_item)
            except ValueError:
              pass
          else:
            try:
              tmpschedlist.index(file_item)
            except ValueError:
              try:
                tmpnoschedlist.index(file_item)
              except ValueError:
                tmpnoschedlist.append(file_item)

    # Find all files/directories which has been discontinued from a previous
    # backup schedule.
    schedlist = []
    discon_schedlist = []
    for file_item in tmpschedlist:
      if file_item:
        for item in self.entry_list:
          update = True
          if re.match(item['path'], file_item):
            basepath = item['path']
            if os.path.isdir(basepath):
              if not re.compile(basepath + '/').match(file_item):
                if not basepath == file_item:
                  update = False
            elif os.path.isfile(basepath):
              if not basepath == file_item:
                update = False
            if update:
              if not item['recursive']:
              #find files with trailing paths
                trailpath = ''
                try:
                  trailpath = re.split('/', re.split(item['path'],
                                                     file_item)[1], 2)[2]
                except IndexError:
                  try:
                    schedlist.index(file_item)
                  except ValueError:
                    schedlist.append(file_item)
                  try:
                    discon_schedlist.remove(file_item)
                  except ValueError:
                    pass
                if trailpath:
                  try:
                    schedlist.index(file_item)
                  except ValueError:
                    try:
                      discon_schedlist.index(file_item)
                    except ValueError:
                      discon_schedlist.append(file_item)
                else:
                  try:
                    schedlist.index(file_item)
                  except ValueError:
                    schedlist.append(file_item)
                  try:
                    discon_schedlist.remove(file_item)
                  except ValueError:
                    pass
              else:
                try:
                  schedlist.index(file_item)
                except ValueError:
                  schedlist.append(file_item)
                try:
                  discon_schedlist.remove(file_item)
                except ValueError:
                  pass
            else:
              try:
                schedlist.index(file_item)
              except ValueError:
                try:
                  discon_schedlist.index(file_item)
                except ValueError:
                  discon_schedlist.append(file_item)

    scheduled_noremovelist = []
    notscheduled_removelist = []
    notbackupedup_removelist = []

    tmpdiscon_schedlist = []
    tmpdiscon_schedlist.extend(discon_schedlist)

    for disc_item in tmpdiscon_schedlist:
      for sched_item in schedlist:
        if re.compile(disc_item + '/').match(sched_item):
          try:
            discon_schedlist.remove(disc_item)
          except ValueError:
            pass

    for item in schedlist:
      scheduled_noremovelist.append(item.split('/', 1)[1])
    for item in discon_schedlist:
      notscheduled_removelist.append(item.split('/', 1)[1])
    for item in tmpnoschedlist:
      notbackupedup_removelist.append(item.split('/', 1)[1])

    # Prepare the list of removable files/directories.
    self.removablelist = []
    self.removablelist.extend(notscheduled_removelist)
    self.removablelist.extend(notbackupedup_removelist)

    # Print some info about removable files (if -s option in command line is
    # specified)
    if self.removablelist:
      if self.show_files:
        self.PrintToFile('o')
        for item in scheduled_noremovelist:
          msg = '\nSCHEDULED        (NO REMOVE) %s' % item
          self.PrintToFile('w', msg=msg)
        for item in notscheduled_removelist:
          msg = '\nDISCONTINUED BACKUP (REMOVE) %s' %  item
          self.PrintToFile('w', msg=msg)
        for item in notbackupedup_removelist:
          msg = '\nNOMATCH             (REMOVE) %s' % item
          self.PrintToFile('w', msg=msg)
      ret_value = True
    else:
      ret_value = False

    return ret_value

  def ComputeDeleteTime(self):
    """Computes and verifies age of a file/directory.

    This function checks ctime of each file in list removablelist and if the
    ctime is greater than the retention_time (specified in config file), then
    the file is marked for deletion. Also prints info to a logfile (if -s
    command line option is specified)
    """

    msg = ('\n')
    self.PrintToFile('w', msg=msg)
    self.deletable_olditems = []
    localtime = time.mktime(time.localtime())

    # Compare each file and check if ctime is > retention_time.
    for item in self.removablelist:
      #lstat does not follow symlinks
      try:
        file_ctime = os.lstat(item)[stat.ST_CTIME]
        file_mtime = os.lstat(item)[stat.ST_MTIME]
      except OSError, e:
        self.loghandle.logger.warning('%s', e)
        continue
      if (localtime - file_ctime) > self.retention_time:
        msg = ('OLDER CTIME: %s (MTIME: %s) %s\n'
               % (time.ctime(file_ctime), time.ctime(file_mtime), item))
        self.PrintToFile('w', msg=msg)
        self.deletable_olditems.append(item)
      else:
        msg = ('NEWER CTIME: %s (MTIME: %s) %s\n'
               % (time.ctime(file_ctime), time.ctime(file_mtime), item))
        self.PrintToFile('w', msg=msg)
    if self.deletable_olditems:
      self.loghandle.logger.info('Found some old files which could be removed.')
      self.DeleteOldFiles()
    else:
      self.loghandle.logger.info('Found no old files which could be removed.')
      self.PrintToFile('c')

  def DeleteOldFiles(self):
    """Deletes old files.

    As the name suggests, this function deletes old files which are also no
    more being backedup (by being not part of the backup schedule). Any
    file/directory present in the list deletable_olditems is to be removed. For
    this the list is sorted so that the list starts with files and then
    traverses the deletable directories from the innermost level to upwards.
    This is required since we use os.remove for removing a file and os.rmdir for
    removing directory. By having the list sorted, we ensure that only empty
    directories get removed. Does a chdir to the backup partition before
    removing files/directories. Also prints info to a logfile (if -s
    command line option is specified)

    Returns:
      False - if fails to do a chdir.
    """

    file_list = []
    dir_list = []
    sorted_olditems = []
    for item in self.deletable_olditems:
      item_mode = os.lstat(item)[stat.ST_MODE]
      if (stat.S_ISREG(item_mode) or
          stat.S_ISLNK(item_mode) or
          stat.S_ISBLK(item_mode) or
          stat.S_ISCHR(item_mode)):
        try:
          file_list.append(item)
        except ValueError:
          pass
      elif stat.S_ISDIR(item_mode):
        try:
          dir_list.append(item)
        except ValueError:
          pass
    # Sort list
    sorted_olditems.extend(file_list)
    dir_list.reverse()
    sorted_olditems.extend(dir_list)
    del file_list
    del dir_list
    del self.deletable_olditems
    for item in sorted_olditems:
      msg = ('\nSORTED OLD          (REMOVE) ' + item)
      self.PrintToFile('w', msg=msg)
    try:
      os.chdir(self.backup_dir)
    except OSError, e:
      self.loghandle.logger.info('%s', e)
      self.PrintToFile('c')
      return False
    # Start deletion process
    for item in sorted_olditems:
      if os.path.isfile(item) or os.path.islink(item):
        try:
          os.remove(item)
        except OSError, e:
          self.loghandle.logger.error('%s', e)
          self.loghandle.logger.error('%s: Failed to remove file: %s',
                                      self.getName(), item)
      elif os.path.isdir(item):
        try:
          os.rmdir(item)
        except OSError, e:
          # Ignore if directory is not empty
          if not e.errno == 39:
            self.loghandle.logger.error('%s', e)
            self.loghandle.logger.error('%s: Failed to remove dir: %s',
                                        self.getName(), item)
    os.chdir('/tmp')
    self.PrintToFile('c')

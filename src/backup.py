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


"""This module does the backup jobs.

backup module takes care of the core functionality of the application which
is, performing a backup. Also includes preparing an rsync command
depending on various options passed, like whether it has to do a full backup,
backup a modified path, recursive backup, non-recursive backup or dry-run.
Further this is done either in a threaded or non-threaded manner.
"""

import sys
import os
import re
import threading

import helper

class Backup:
  """Class which provides methods to perform backups."""

  def __init__(self, backupdir, backupbinary, excfile, entry,
               modified_path=None, log_handle='', dryrun=False, 
               sh_var=None):
    """Initialise environment, which includes setting rsync options list.

    Args:
      backupdir: String - path of the backup directory
      backupbinary: String - the rsync binary path
      excfile: String - The filename whihc contains the exclude entries.
      entry: List - List of entries. Each entry is a dictionary.
      modified_path: List - Paths which were modified. ()
      log_handle: Object - Handle to the logging object.
      dryrun: Boolean - used to specify whether rsync should be executed with a
        "--dry-run" option or not
      sh_var: List - SSH Variables required when backup method is RSYNC.
    """

    self.backupbinary = backupbinary
    self.backupdir = backupdir
    self.excludefile = excfile
    self.entry = entry
    self.name = entry['name']
    self.modfied_path = modified_path
    try:
      self.entry_exc = entry['exclude']
    except KeyError:
      self.entry_exc = None
    try:
      self.entry_inc = entry['include']
    except KeyError:
      self.entry_inc = None
    self.backupdestination = self.backupdir + self.entry['path']
    # Options passed to rsync
    self.rsync_options = {
        'dryrun_o': '--dry-run',
        'relative_o': '--relative',
        'norecursive_o': '-d',
        'recursive_o': '-r',
        'excludefile_o': '--exclude-from=',
        'prsvlinks_o': '--links',
        'prsvperm_o': '--perms',
        'prsvtime_o': '--times',
        'prsvown_o': '--owner',
        'prsvgrp_o': '--group',
        'prsvdvc_o': '--devices',
        'update_o': '--update',
        'delete_o': '--delete',
        'deleteafter_o': '--delete-after',
        'deleteexc_o': '--delete-excluded',
        'tempdir_o': '--temp-dir=',
        'forcedel_o': '--force',
        'shell_o': '-e',
	'backup_o' : '-b',
	'backup_suffix_o' : '--suffix=',
	'backup_suffix_extn' : '.odb~'
    }
    self.dryrun = dryrun
    self.logmsg = log_handle
    self.maintainprevious = self.logmsg.maintainprevious
    self.shellvar = sh_var
    if self.shellvar:
      self.sshpath = self.shellvar[0]
      self.sshport = self.shellvar[1]
      self.sshuser = self.shellvar[2]
      self.sshserver = self.shellvar[3]
      self.ssh_cmd = [self.sshpath, '-l', self.sshuser, '-p', self.sshport,
                      self.sshserver]
    self.help_backup = helper.CommandHelper(self.logmsg)

  def VerifyBackup(self):
    """Checks whether the entry path (source) exists at the destination.

    This check is run during the initial stages before the file monitoring
    starts.

    Returns:
      backupretval: Integer - Is the exit value obtained from the command.
    """
    if self.shellvar:
      # This check is duplicated in CreateBackupDirStruct, VerifyBackupStructure
      # Costly. Not doing this check if backup method is RSYNC.
      pass
    else:
      if os.path.exists(self.backupdestination):
        self.logmsg.logger.info('%s has been backedup before', self.name)
      else:
        self.logmsg.logger.info('Performing the very first backup of: %s',
                                self.name)
    self.logmsg.logger.warning('Please wait while %s is being backed up',
                                 self.name)
    # Perform the backup process
    self.DoBackup()

    if not self.backupretval:
      self.logmsg.logger.info('Backup of entry %s to backup drive completed'
                              ' successfully.', self.name)
    else:
      self.logmsg.logger.error('Backup of entry %s failed. Error code: %s',
                               self.name, self.backupretval)
    return self.backupretval

  def DoBackup(self):
    """The code that does the rsync command generation.

    Also performs the actual backup. Backup is done in a sequential manner,
    with each call to RunCommandPopen waiting for the rsync command to be 
    completed. RunCommandPopen (Helper) returns exit value of the rsync command.

    Returns:
      backupretval: Integer - Is the exit value obtained from the command
    """

    cmdarglist = []

    if not self.modfied_path:
      tmpsource = self.entry['path']
    else:
      tmpsource = self.modfied_path
    backupsource = os.path.normpath(os.path.expanduser(tmpsource))
    backupdest = self.backupdir
    if self.dryrun:
      cmdarglist.extend([self.backupbinary,
                         self.rsync_options['dryrun_o']])
    else:
      cmdarglist.extend([self.backupbinary])

    if self.shellvar:
      shelloptions = [self.rsync_options['shell_o'], self.sshpath + ' -p ' +
                     self.sshport]
      cmdarglist.extend(shelloptions)

    if self.entry['recursive']:
      cmdarglist.extend([self.rsync_options['recursive_o']])
    else:
      if not os.path.isfile(backupsource):
        backupsource += '/'
      cmdarglist.extend([self.rsync_options['norecursive_o']])

    if self.entry_exc:
      for exc_item in self.entry_exc:
        if exc_item:
          cmdarglist.extend(['--exclude=' + exc_item])
    if self.entry_inc:
      for inc_item in self.entry_inc:
        if inc_item:
          cmdarglist.extend(['--include=' + inc_item])

    if self.maintainprevious:
      cmdarglist.extend([self.rsync_options['backup_o'], 
                        self.rsync_options['backup_suffix_o'] +
			self.rsync_options['backup_suffix_extn']])
    else:
      cmdarglist.extend([self.rsync_options['delete_o'],
                         self.rsync_options['deleteafter_o']])
    
    if cmdarglist:
      cmdarglist.extend([self.rsync_options['relative_o'],
                         self.rsync_options['prsvlinks_o'],
                         self.rsync_options['prsvperm_o'],
                         self.rsync_options['prsvtime_o'],
                         self.rsync_options['prsvown_o'],
                         self.rsync_options['prsvgrp_o'],
                         self.rsync_options['prsvdvc_o'],
                         self.rsync_options['tempdir_o'] + '/tmp',
                         self.rsync_options['update_o'],
                         self.rsync_options['deleteexc_o'],
                         self.rsync_options['forcedel_o'],
                         self.rsync_options['excludefile_o'] +
                         self.excludefile, backupsource])
      if self.shellvar:
        cmdarglist.extend([self.sshuser + '@' + self.sshserver + ':' 
                           + backupdest])
      else:
        cmdarglist.extend([backupdest])
    else:
      self.logmsg.logger.warning('No command')
      return None

    self.logmsg.logger.debug('%s', cmdarglist)

    self.backupretval = self.help_backup.RunCommandPopen(cmdarglist)
    if self.backupretval < 0:
      self.logmsg.logger.warning('%s Terminated, Err code: %s', self.name,
                                self.backupretval)

    return self.backupretval


class AsyncBackup(threading.Thread):
  """Class which provides methods to perfrom backups in a new thread."""

  def __init__(self, backupdir, backupbinary, excfile, entrylist,
               pathslist, log_handle, sh_var=None):
    """Initialise thread and backup environment.

    Args:
      backupdir: String - path of the backup directory
      backupbinary: String - the rsync binary path
      excfile: String - The filename whihc contains the exclude entries.
      entrylist: List - List of entries. Each entry is a dictionary.
      pathslist: List - Paths which were modified.
      log_handle: Object - Handle to the logging object.
      sh_var: List - SSH parameters list
    """

    threading.Thread.__init__(self, name='AsyncBackup')
    self.destdir = backupdir
    self.binary = backupbinary
    self.exc_file = excfile
    self.pathslist = pathslist
    self.entry_list = entrylist
    self.loghandle = log_handle
    self.ssh_var = sh_var

  def run(self):
    """Starts the a brand new thread for backup.

    Backup all paths populated in list (modified_path) by
    FindEntries() function.
    """

    self.FindEntries(self.pathslist, self.entry_list)

    failedbackup = 0
    fblist = []
    counter = 0

    for entry in self.matched_entry:
      path = self.modified_path[counter]
      asyncbackupstart = Backup(self.destdir, self.binary,
                                self.exc_file, entry, modified_path=path,
                                log_handle=self.loghandle,
                                dryrun=self.loghandle.dryrun,
                                sh_var=self.ssh_var)
      retcode = asyncbackupstart.DoBackup()
      counter += 1
      path = None
      # Here the number of failed backups are calculated by checking the return
      # code from asyncbackupstart.DoBackup function.
      if not retcode:
        self.loghandle.logger.info('Backup of entry %s completed'
                                   ' successfully.', entry['name'])
      else:
        self.loghandle.logger.error('Backup of entry %s failed.',
                                    entry['name'])
        failedbackup += 1
        fblist.append(entry['name'])

    # Print message if backups are failing
    if failedbackup >= len(self.matched_entry):
      self.loghandle.logger.critical('Almost all backups failed: %s', fblist)
      self.loghandle.logger.critical('Please investigate.')
      # Add a GUI dialog here. (TODO)

  def FindEntries(self, pathslist, entrylist):
    """Find all modified paths that match any corresposnding entry path.

    Append them to a list (modified_path).

    Args:
      pathslist: List - List of file/directory paths that got modifed.
      entrylist: List - List of entries. Each entry is a dictionary.
    """

    self.tmplist = []
    self.modified_path = []
    self.matched_entry = []
    for entry in entrylist:
      for path in pathslist:
        if re.match(entry['path'], path):
          self.tmplist.append(path)
          try:
            self.matched_entry.index(entry)
          except ValueError:
            self.matched_entry.append(entry)
      if self.tmplist:
        prefx = self.CommonDirPrefix(self.tmplist)
        self.modified_path.append(prefx)
        self.tmplist = []

  def CommonDirPrefix(self, dirlist):
    """Given a list of pathnames, returns the longest common leading directory.

    Works similar to os.path.commonprefix which does a character matching.

    Args:
      dirlist: List - List of directory paths

    Returns:
      path: String - The common leading directory path among the list paths
        passed as the argument.
    """

    if not dirlist:
      return ''
    smallstr = min(dirlist)
    bigstr = max(dirlist)
    str_len = min(len(smallstr), len(bigstr))
    small_list = re.split('/', smallstr)
    big_list = re.split('/', bigstr)
    list_len = min(len(small_list), len(big_list))
    path = '/'
    for i in xrange(list_len):
      if small_list[i] != big_list[i]:
        for j in xrange(i):
          if small_list[j]:
            path = path + small_list[j] + '/'
        return os.path.normpath(path)
    return bigstr[:str_len]

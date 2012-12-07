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

"""Config loader, initializer and sanity checker.

init module has many functions to be done, which include read the
config file, sanity checking, inititalise parameters, initialise the logging
system and the command line argument parser.
"""

import os
import platform
import re
import sys

import logger
import helper

try:
  import yaml
except ImportError, strerror:
  print 'Error: %s' % (strerror)
  print 'Please install PyYaml for YAML support'
  print 'http://pyyaml.org/wiki/PyYAML'
  print 'Quitting!'
  sys.exit(1)


class InitData:
  """This class does all the initialisation part for the application.

  Also provide methods to check mount status.
  """

  def __init__(self, conffile):
    """Start logging and initialise required parameters."""

    self.log = logger.LogArgManager()
    self.log.LogInit()
    self.log.logger.info('Started logger')
    self.log.GetArgs()
    self.log.logger.info('Starting initialiser.')
    if self.log.arg_conffile:
      self.config_file = os.path.normpath(
          os.path.expanduser(self.log.arg_conffile))
    else:
      self.config_file = os.path.normpath(os.path.expanduser(conffile))
    self.user = os.getlogin()
    self.hostname = platform.node().split('.')[0]
    verify = helper.CommandHelper(self.log)
    self.help_execute = verify
    # Make sure we have rsync available
    self.log.logger.debug('Looking for rsync executable.')
    self.rsync_path = 'rsync'
    if verify.RunCommandPopen([self.rsync_path, '--version']):
      self.log.logger.error('Cannot find a rsync executable.')
      self.log.logger.error('Make sure rsync is in your $PATH')
      sys.exit(1)
    # Make sure we have mount and umount commands available
    self.mountbinary = "mount"
    self.log.logger.debug('Looking for mount command.')
    if verify.RunCommandPopen([self.mountbinary, '--version']):
      self.log.logger.error('Cannot find a mount executable.')
      self.log.logger.error('Make sure mount is in your $PATH')
      sys.exit(1)
    self.umountbinary = "umount"
    self.log.logger.debug('Looking for umount command.')
    if verify.RunCommandPopen([self.umountbinary, '--version']):
      self.log.logger.error('Cannot find umount command')
      self.log.logger.error('Make sure umount is in your $PATH')
      sys.exit(1)
    # The external app which is used for showing GUI popup message box.
    # Need to replace this with python-gtk (TODO)
    self.gui_helper = 'zenity'
    self.noguihelper = False
    self.gui_helperpid = None
    self.log.logger.debug('Looking for zenity command.')
    if verify.RunCommandPopen([self.gui_helper, '--version']):
      self.log.logger.warning('Cannot find GUI Helper %s', self.gui_helper)
      self.noguihelper = True

  def ConfigLoader(self):
    """Read config file.

    Reads the yaml formatted config file (default: ./config.yaml) into a
    dictionary variable configdata. Performs checking of the global,
    exclude and entry sections of the config file. Initialises the program
    accordingly by calling the functions InitGlobalData, InitExcludeData and
    InitEntryData.

    The default config file is ./config.yaml. If that is not found,
    ~/.openduckbill/config.yaml is checked. If that too is missing, user is
    prompted to enter the path to the config file by using command line
    argument passing.

    Returns:
      Lists - four lists, globallist, methodlist, excludelist and entrylist
        are returned, which on the other hand are created by calling
        InitGlobalData, InitExcludeData and InitEntryData respectively.
    """

    self.log.logger.info('==> Using config file: %s', self.config_file)

    if os.access(self.config_file, os.F_OK|os.R_OK):
      try:
        readhandle = file(self.config_file, 'r')
      except IOError, e:
        self.log.logger.error('%s, %s', self.config_file, e.strerror)
    else:
      self.log.logger.warning('Unable to use config file: %s',
                              self.config_file)
      self.config_file = os.path.normpath(
          os.path.expanduser(self.log.defconfig))
      self.log.logger.warning('Trying to use alternate config file: %s',
                              self.config_file)
      try:
        readhandle = file(self.config_file, 'r')
      except IOError, e:
        self.log.logger.error('%s, %s', self.config_file, e.strerror)
        sys.exit(1)
    try:
      self.configdata = yaml.load(readhandle)
      readhandle.close()
    except (yaml.scanner.ScannerError, yaml.parser.ParserError,
            yaml.constructor.ConstructorError), e:
      self.log.logger.error('Error in configuration file: %s, %s',
                            self.config_file, e)
      sys.exit(1)
    self.glist, self.methlist = self.InitGlobalData()
    self.exclist = self.InitExcludeData()
    self.enlist = self.InitEntryData()
    return

  def InitGlobalData(self):
    """Read global data from config.

    Reads data from the global key of the dictionary configdata, which was
    populated in function ConfigLoader. Following actions are performed here
      - Invokes functions to does some sanity check depending on backup
        method selected
      - Verify value provided for syncinterval
        - Defaults to 300 seconds, if not provided
      - Verify value provided for commitchanges
        - Defaults to 64, if not provided
      - Verify value provided for maintainprevious
        - Defaults to False, if not provided
      - Verify value provided for retainbackup
        - Defaults to True, if not provided
      - Verify value provided for retentiontime
        - Defaults to 604800 (seven days), if not provided

    Returns:
      globallist: List - List of global parameters declared in Global section
        of config.yaml, Format as below:
        [
          'Backup method',                      # String
          syncinterval,                         # Integer
          commitchanges,                        # Integer
          'Backup directory path',              # String
          retentiontime,                        # Integer
          retainbackups                         # Boolean
          maintainprevious                        # Boolean
        ]
      methodlist: List - Details of backup server
        [
          'NFS Backup server',                  # String
          'Remote mount',                       # String
          'Local mount',                        # String
        ]
    """

    try:
      self.backupmethod = self.configdata['global']['backupmethod']
      if self.backupmethod is None:
        raise KeyError
    except KeyError:
      self.log.logger.error('Please define global variable "backupmethod".'
                            ' Supported values LOCAL | NFS | RSYNC')
      sys.exit(1)
    self.backupmethod = self.backupmethod.upper()
    if self.backupmethod == "NFS":
      self.InitMethodData(self.backupmethod)
    elif self.backupmethod == "RSYNC":
      self.InitMethodData(self.backupmethod)
    elif self.backupmethod == "LOCAL":
      self.InitMethodData(self.backupmethod)
    else:
      self.log.logger.error('Invalid global variable "backupmethod" defined.'
                            'Supported values LOCAL | NFS | RSYNC')
      sys.exit(1)
    try:
      self.syncinterval = self.configdata['global']['syncinterval']
      if self.syncinterval is None or not self.syncinterval:
        self.syncinterval = 300  # 5 Minutes
        raise KeyError
      try:
        self.syncinterval = int(self.syncinterval)
      except ValueError:
        raise KeyError
      if self.syncinterval < 5:
        self.log.logger.warning('Global variable "syncinterval" defined is too'
                                ' small. (must be > 5)')
        raise KeyError
    except KeyError:
      self.syncinterval = 300
      self.log.logger.warning('Please define a valid global variable'
                              ' "syncinterval"')
      self.log.logger.warning('Using default: %s seconds', self.syncinterval)
    try:
      self.commitchanges = self.configdata['global']['commitchanges']
      if self.commitchanges is None or not self.commitchanges:
        self.commitchanges = 64
        raise KeyError
      try:
        self.commitchanges = int(self.commitchanges)
      except ValueError:
        raise KeyError
      if self.commitchanges < 5:
        self.log.logger.warning('Global variable "commitchanges" defined is'
                                ' too small. (must be > 5)')
        raise KeyError
    except KeyError:
      self.commitchanges = 64
      self.log.logger.warning('Please define a valid global variable'
                              ' "commitchanges"')
      self.log.logger.warning('Using default: %s', self.commitchanges)
    try:
      maintainprevious = self.configdata['global']['maintainprevious']
      if not self.CheckKeyValue(maintainprevious):
        raise KeyError
    except KeyError:
      self.log.logger.warning('Invalid or no "maintainprevious" key value defined')
      self.log.logger.warning('Assuming "no"')
      maintainprevious = False
    self.log.maintainprevious = maintainprevious
    try:
      self.retainbackup = self.configdata['global']['retainbackup']
      if not self.CheckKeyValue(self.retainbackup):
        raise KeyError
    except KeyError:
      self.log.logger.warning('Invalid or no "retainbackup" key value defined')
      self.log.logger.warning('Assuming "yes"')
      self.retainbackup = True
    if self.backupmethod == "RSYNC":
      if not self.retainbackup:
        self.log.logger.warning('Deleting old files is not supported yet, in'
                                ' backup method: RSYNC.')
        self.retainbackup = True
    if maintainprevious:
      self.log.logger.warning('Disabling "retainbackup"')
      self.retainbackup = True
    try:
      self.retentiontime = self.configdata['global']['retentiontime']
      if self.retentiontime is None or not self.retentiontime:
        raise KeyError
      try:
        self.retentiontime = int(self.retentiontime)
      except ValueError:
        raise KeyError
    except KeyError:
      self.retentiontime = 604800
      self.log.logger.warning('Please define a valid global variable'
                              ' "retentiontime"')
      self.log.logger.warning('Using default: %s', self.retentiontime)
    self.fuserbinary = '/usr/bin/fusermount'
    self.globallist = []
    self.methodlist = []
    if self.backupmethod == "RSYNC":
      self.backupdirpath = os.path.join(self.remotemount, self.user,
                                        '__backups__', self.hostname)
    else:
      self.backupdirpath = os.path.join(self.localmount, self.user,
                                        '__backups__', self.hostname)
    self.globallist.extend([self.backupmethod, self.syncinterval,
                            self.commitchanges, self.backupdirpath,
                            self.retentiontime, self.retainbackup,
                            maintainprevious])
    self.methodlist.extend([self.backupserver, self.remotemount,
                            self.localmount])
    return self.globallist, self.methodlist

  def InitMethodData(self, method):
    """Initialize variables depending on the backup method specified in
    config

    Args:
      method : String - Backup method as read from config file
    """

    try:
      methodsection = self.configdata[method]
      if methodsection is None:
        raise KeyError
    except KeyError:
      self.log.logger.error('Please define section "%s"', method)
      sys.exit(1)
    try:
      self.backupserver = self.configdata[method]['server']
      if self.backupserver is None:
        raise KeyError
    except KeyError:
      if method != "LOCAL":
        self.log.logger.error('Please define variable "server"'
                              ' in section "%s"', method)
        sys.exit(1)
      else:
        self.backupserver = ""
    try:
      self.remotemount = self.configdata[method]['remotemount']
      if self.remotemount is None:
        raise KeyError
    except KeyError:
      if method != "LOCAL":
        self.log.logger.error('Please define variable "remotemount"'
                              ' in section "%s"', method)
        sys.exit(1)
      else:
        self.remotemount = ""
    if method != "RSYNC":
      try:
        self.localmount_tmp = self.configdata[method]['localmount']
        if self.localmount_tmp is None:
          raise KeyError
        self.localmount = os.path.normpath(
            os.path.expanduser(self.localmount_tmp))
        if os.path.isdir(self.localmount):
          pass
        else:
          self.log.logger.error('The "localmount" defined in configfile is'
                                ' not a directory.')
          sys.exit(1)
      except KeyError:
        self.log.logger.error('Please define variable "localmount"'
                              ' in section "%s"', method)
        sys.exit(1)
    else:
      self.localmount = ""
    if method == "NFS":
      try:
        self.nfsoptions = self.configdata[method]['nfsmountoptions']
        if self.nfsoptions is None:
          raise KeyError
      except KeyError:
        self.nfsoptions = None
    elif method == "RSYNC":
      try:
        self.sshport = str(self.configdata[method]['sshport'])
        if self.sshport is None:
          raise KeyError
      except KeyError:
        self.sshport = '22'
      try:
        self.sshuser = self.configdata[method]['sshuser']
        if self.sshuser is None:
          raise KeyError
      except KeyError:
        self.sshuser = self.user
      self.ssh_path = 'ssh'
      if self.help_execute.RunCommandPopen([self.ssh_path, '-V']):
        self.log.logger.error('Cannot find an ssh executable.')
        self.log.logger.error('Make sure ssh is in your $PATH')
        self.log.logger.error('We run rsync over ssh!')
        sys.exit(1)
      self.ssh_cmd = [self.ssh_path, '-l', self.sshuser, '-p', self.sshport,
                      self.backupserver]


  def CheckKeyValue(self, param):
    """Checks boolean value of the parameter passed.

    YAML reads "yes|no" as "True|False" and anything else as a
    string, so we need to make sure the config contains "yes|no" and
    not something else.

    Args:
      param: Boolean - Value read from YAML config file
    Returns:
      Boolean - True if the param is either True|False else returns False
    """
    if param == True:
      pass
    elif param == False:
      pass
    elif param is None:
      return False
    else:
      return False
    return True

  def InitExcludeData(self):
    """Read exclude file/directories from config.

    Creates a list which contains the files/directories and/or the REGEXes
    defined in config file. This list is read out of the dictionary configdata
    (the exclude key) which gets initialised in function ConfigLoader. It is ok
    to have no excludes.

    Returns:
      excludelist: List - List of excluded files/directories/REGEXes
    """

    try:
      tmpexcludelist = self.configdata['exclude']
      if tmpexcludelist:
        self.excludelist = []
        for item in tmpexcludelist:
          self.excludelist.append(item)
      else:
        raise KeyError
    except KeyError:
      self.log.logger.info('No exclude paths defined')
      return
    return self.excludelist

  def InitEntryData(self):
    """Read entries from config.

    Reads in data from the entry key of the dictionary configdata,
    which was earlier populated in function ConfigLoader. Following actions are
    performed here:
      Sanity Checks:
      - Check whether at least one entry is defined
      - Check whether path has been mentioned in an entry
      - Check if path mentioned in config file is valid
        - Check whether user has read permissions on the path (does not recurse
          into the path)
      - Check whether name has been mentioned in an entry
      - Check whether at least one valid entry is defined
      - Check if recursive key is specified and is valid (True|False)
        - If not specified, default it to False
      - Make sure, no two entries have same path specified for backup. (Marks
        as duplicate)
      - Make sure that directories in an entry specified for backup is not
        already part of another recursive backup of its parent directory.
      - Check and do sanity checks on exclude and include entries specified.

    Returns:
      entrylist: List - List of valid entries. Each entry is a dictionary and
      has the following format:
        {
          'path': 'Filesystem path', # String
          'name': 'Name',            # String
          'recursive': True|False    # Boolean
          'exclude':                 # List - Optional
          'include':                 # List - Optional
        }
    """

    try:
      tmpentrylist = self.configdata['entry']
    except KeyError:
      self.log.logger.error('Please define at least one entry to back up in'
                            ' "entry" section')
      sys.exit(1)
    if tmpentrylist:
      self.entrylist = []
      for item in tmpentrylist:
        try:
          path = os.path.abspath(os.path.expanduser(item['path']))
        except KeyError:
          self.log.logger.error('Please define a path for entry: %s',
                                item['name'])
          sys.exit(1)
        tmppath = item['path']
        if os.path.exists(path):
          # We'll keep the absolute path
          item['path'] = path
          try:
            if item['name']:
              # Checking if name key is given or not
              pass
            elif item['name'] is None:
              raise KeyError
          except KeyError:
            self.log.logger.error('Please define a valid entry "name" for'
                                  ' path: %s', tmppath)
            sys.exit(1)
          try:
            if not self.CheckKeyValue(item['recursive']):
              raise KeyError
          except KeyError:
            self.log.logger.warning('Invalid or no "recursive" key value'
                                    ' defined for entry: %s', item['name'])
            self.log.logger.warning('Assuming "recursive" key to be "no"')
            item['recursive'] = False
          if os.access(path, os.F_OK|os.R_OK):
            self.entrylist.append(item)
          else:
            self.log.logger.warning('Path %s defined in %s entry does not have'
                                    ' read permission', item['path'],
                                    item['name'])
            self.log.logger.warning('Entry "%s" ignored', item['name'])
        else:
          self.log.logger.warning('Invalid path "%s" defined in entry: %s',
                                  item['path'], item['name'])
          self.log.logger.warning('Entry "%s" ignored', item['name'])
    else:
      self.log.logger.error('Please define at least one entry to back up in'
                            ' "entry" section')
      sys.exit(1)

    if self.entrylist:
      for item in self.entrylist:
        # Make sure we do not have multiple entries with same paths.
        dupcount = 0
        entrynames = []
        chkpath = item['path']
        for dupitem in self.entrylist:
          if chkpath == dupitem['path']:
            dupcount += 1
            entrynames.append(dupitem['name'])
        if dupcount > 1:
          self.log.logger.error('Path %s is duplicated in entries: %s',
                                chkpath, entrynames)
          self.log.logger.error('Each entry should have one unique path'
                                ' defined. Fix this.')
          sys.exit(1)  # Exits at the first instance of a duplicate etnry

      # Inform user if there are directories being backed up, which
      # are already being backed up by recursive backup of its parent
      # directory.
      recurse_paths = []
      recurse_value = []
      subdircount = 0
      for entry in self.entrylist:
        recurse_paths.append(entry['path'])
        recurse_value.append(entry['recursive'])
      for path in recurse_paths:
        for otherpath in recurse_paths:
          if path is not otherpath:
            # check if there is pattern match
            if re.compile(path + '/').match(otherpath):
              # is this path being recursively backed up?
              if recurse_value[recurse_paths.index(path)]:
                if os.path.isdir(otherpath):
                  self.log.logger.error('%s is a subdirectory of %s',
                                        otherpath, path)
                else:
                  self.log.logger.error('%s is a sub path of %s',
                                        otherpath, path)
                self.log.logger.error('%s is already being recursively backed'
                                      ' up', path)
                self.log.logger.error('This would unnecessarily eat up your'
                                      ' backup disk quota.')
                subdircount += 1
      del recurse_value
      del recurse_paths
      if subdircount:
        sys.exit(1)
      return self.entrylist
    else:
      self.log.logger.error('None of the entries defined have valid paths.')
      sys.exit(1)

  def IsBackupPartitionMounted(self, mount=False):
    """Check whether the backup partition needs to be mounted or not.

    Used when NFS based backup method is selected.

    Args:
      mount: Boolean - Default to false

    Returns:
      mountreq: Boolean - True if partition needs to be mounted, else return
        False
    """

    if self.backupmethod == "NFS":
      self.remote_info = self.backupserver + ":" + self.remotemount
    elif self.backupmethod == "LOCAL":
      # LOCAL : Directory check has already completed in InitMethodData
      # We assume that the local backup directory always exist.
      return False
    elif self.backupmethod == "RSYNC":
      # RSYNC: No local mount required 
      return False
    local_mountpoint = self.localmount
    mountreq = mount
    # We use this instead of os.path.ismount, since we need to find the
    # filesystem type too.
    dfcmd = 'df -h ' + local_mountpoint
    dfhandle = os.popen(dfcmd, 'r')
    dfhandle.readline()  # Skip first line
    try:
      filesystem = dfhandle.readline().split(None, 5)[0]
    except IndexError:
      filesystem = None
    if filesystem == self.remote_info:
      pass
    elif filesystem != self.remote_info:
      self.log.logger.warning('%s defined in configfile is not mounted'
                              ' in %s', self.remotemount, local_mountpoint)
      mountreq = True
    dfhandle.close()
    return mountreq

  def UnmountPartition(self):
    """Unmount backup partition.

    This function unmounts the given mountpoint using the unmount command.
    This is done by using the methid call RunCommandPopen.

    Returns:
      unmountretval: Integer - Return code of the command execution
    """

    if self.backupmethod == "NFS":
      cmd = [self.umountbinary, "-l", self.localmount]
    retval = self.help_execute.RunCommandPopen(cmd)
    return retval

  def MountPartition(self):
    """Mount backup partition.

    This function attempts to mount the backup partition.
    Then, RunCommandPopen method is used to execute the
    command. RunCommandPopen method waits for the command completion and
    gets the return code of the command. If the command has failed, then
    app exits with appropriate error messages.


    Returns:
      mountretval: Integer - return code from command execution done using
        RunCommandPopen method
    """

    self.UnmountPartition()
    if self.backupmethod == "NFS":
      cmd = [self.mountbinary, self.localmount]
      # mount server:remotemount localmount won't work as this requires user to be root
      #if self.nfsoptions:
      #  cmd = [self.mountbinary, "-t", "nfs", "-o", self.nfsoptions,
      #         self.remote_info, self.localmount]
      #else:
      #  cmd = [self.mountbinary, "-t", "nfs", self.remote_info, self.localmount]
      self.log.logger.warning('Mounting NFS backup partition.')

    retval = self.help_execute.RunCommandPopen(cmd)
    if retval == 1 and self.backupmethod == "NFS":
      self.log.logger.warning('Mount command failed.')
    if retval == 0:
      # Double checking for a mounted NFS partition
      if self.IsBackupPartitionMounted():
        self.log.logger.warning('Mount failed.')
      else:
        self.log.logger.info('Successfully mounted %s as %s partition.',
                             self.methlist[1], self.backupmethod)
    else:
      self.log.logger.error('Unable to mount partition.')
      self.log.logger.warning('Make sure you have the following line in your'
                           ' /etc/fstab')
      if self.nfsoptions:
        self.log.logger.warning('%s  %s  nfs  %s,user,auto 0 0',
                                self.remote_info, self.localmount,
                                self.nfsoptions)
      else:
        self.log.logger.warning('%s  %s  nfs  user,auto 0 0',
                                self.remote_info, self.localmount)

      sys.exit(1)
    return retval

  def VerifyBackupDirStruct(self, structok=False):
    """Verify backup directory structure in backup partition.

    Checks whether backupdirpath exists or not.

    Args:
      structok: Boolean - To set default to False.

    Returns:
      Boolean - False if there is need to create a backup directory, else
        return True.
    """

    if self.backupmethod != "RSYNC":
      if (os.path.isdir(self.backupdirpath) &
          os.access(self.backupdirpath, os.W_OK)):
        structok = True
      else:
        structok = False
      return structok
    else:
      cmd = []
      cmd.extend(self.ssh_cmd)
      ssh_exec_cmd = ['test', '-d', self.backupdirpath]
      cmd.extend(ssh_exec_cmd)
      self.log.logger.debug(cmd)
      retval = self.help_execute.RunCommandPopen(cmd)
      if retval:
        structok = False
      else:
        structok = True
      return structok


  def CreateBackupDirStruct(self):
    """Create the backup directory structure.

    Directory path = "<partition>/<username>/__backups__/<hostname>/"

    Returns:
      Boolean - True if directory creation succeeded, else False.
    """

    if self.backupmethod != "RSYNC":
      try:
        # Recursive directory path creation
        os.makedirs(self.backupdirpath, 0700)  
        self.log.logger.info('Created backup directory structure.')
      except OSError, e:
        self.log.logger.error('%s', e)
        self.log.logger.error('Unable to create backup directory structure.')
        return False
      return True
    else:
      cmd = []
      cmd.extend(self.ssh_cmd)
      if self.log.debug:
        ssh_exec_cmd = ['mkdir', '-pv', '--mode=0700', self.backupdirpath]
      else:
        ssh_exec_cmd = ['mkdir', '-p', '--mode=0700', self.backupdirpath]
      cmd.extend(ssh_exec_cmd)
      self.log.logger.debug(cmd)
      retval = self.help_execute.RunCommandPopen(cmd)
      if retval:
        self.log.logger.error('Unable to create backup directory structure '
                              'in rsync server')
        return False
      else:
        self.log.logger.info('Created backup directory structure in rsync '
                             'server.')
        # We need to make the permissions a bit more stricter while creation.
        userpath = os.path.dirname(os.path.dirname(self.backupdirpath))
        cmd = []
        cmd.extend(self.ssh_cmd)
        if self.log.debug:
          ssh_exec_cmd = ['chmod', '-v', '0700', userpath]
        else:
          ssh_exec_cmd = ['chmod', '0700', userpath]
        cmd.extend(ssh_exec_cmd)
        self.log.logger.debug(cmd)
        retval = self.help_execute.RunCommandPopen(cmd)
        if retval:
          self.log.logger.error('Could not fix permissions on backup path')
        else:
          self.log.logger.info('Fixed permissions on backup path')
        return True

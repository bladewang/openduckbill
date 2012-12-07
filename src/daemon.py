#!/usr/bin/python2.4

# Copyright 2008 Google Inc.
# Author : Anoop Chandran <anoopj@google.com>
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


"""Read config file, initialise, perform backups, daemonise, file monitoring.

The core module of the application which does does everything. Reads the
config file, initialises the environment, mounts backup partition if required
create a daemon program, start file monitoring and backup data which gets
modified.

Briefly, the functionalities:
    - Initialise application environment
    - Perform initial sequential backup
    - Create exclude file
    - Fork to background to run as a daemon
    - Create timer thread for backup
    - Create timer thread for deleting unscheduled files/directories in backup
      partition (supported in local or NFS backup modes only)
    - Initialise filesytem monitoring
    - Do signal handling
    - Verify if filesystem changes have occured and backup needs to be done
    - Start separate thread to perform backup
    - Do cleanup operations on an error condition or after receiving a signal.
    - Show GUI messages to inform user about error conditions
    - Print debug and resource usage information.
    - Filesystem monitoring.
"""

import os
import resource
import signal
import sys
import tempfile
import threading

import backup
import deletor
import init

try:
  import pyinotify
except ImportError, strerror:
  print 'Error: %s' % (strerror)
  print 'Please install pyinotify for inotify support'
  print 'http://pyinotify.sourceforge.net/'
  print 'Quitting!'
  sys.exit(1)


class OpenDuckbillMain(init.InitData):
  """Class provides methods for doing the core functionalities."""

  def __init__(self, conffile):
    """Initialise environment.

    Args:
      conffile: String - config file
    """

    init.InitData.__init__(self, conffile)

  def MainInitialize(self):
    """Does the initialisation and verification for the application.

    Initialisation include, fetching the global, exclude, entry and backup
    method details. Also mounts the NFS backup partition (verified using function
    IsBackupPartitionMounted) if required (by invoking function MountPartition),
    create the backup directory structure (verified using VerifyBackupDirStruct)
    if required (using function CreateBackupDirStruct)

    Returns:
      True - If all checks complete and successful.
    """

    # Perform initial checks like duplicate paths, subdirectory check, path
    # exist etc.
    self.ConfigLoader()
    if self.IsBackupPartitionMounted():
      # Backup partition not mounted? then mount it.
      if not self.MountPartition():
        # Mounted partition? Now check the directory structure
        self.createpath = self.VerifyBackupDirStruct()
    else:
      # Partition already mounted? then check the directory structure
      if self.backupmethod == "LOCAL":
        self.log.logger.info('Starting backup on %s as %s partition ',
                             self.methlist[2], self.glist[0])
      elif self.backupmethod != "RSYNC":
        self.log.logger.info('%s mounted already as %s partition',
                             self.methlist[1], self.glist[0])
      self.createpath = self.VerifyBackupDirStruct()
    if self.createpath:
      # Our directory struture is ok. Start backup modules.
      self.log.logger.info('Completed sanity checks.')
    else:
      # Our directory structure is NOT ok. Fix it.
      if not self.CreateBackupDirStruct():
        sys.exit(1)
      # Created directory structure.
      self.log.logger.info('Completed sanity checks.')
    return True

  def BackupInitialize(self):
    """Starts the backup process.

    Wrapper function which does following operations:
      - Create the global exclude file for backup
      - Do a sequential initial backup entries
      - Fork to background and become a daemon
    """

    self.CreateExclude()
    self.BackupEntry()
    self.CreateServerThread()

  def CreateExclude(self):
    """Creates a file with excluded files/directories/patterns.

    All files/directories/REGEXes mentioned in the exclude section of the config
    file is in the list excludelist. This function creates a temporary file in
    the "/tmp" with contents of excludelist. This file is later used for
    excluding files/directories/REGEXes while a backup is performed (in
    BackupEntry and StartAsyncBackupThread)
    """

    try:
      exlist_tmpfile, self.exlist_tmpname = tempfile.mkstemp('.glbexclude',
                                                             'tmp-', '/tmp/',
                                                             '')
    except OSError, e:
      self.log.logger.critical('%s', e)
      sys.exit(1)
    try:
      if self.excludelist:
        for tmpexc_item in self.excludelist:
          exc_item = os.path.normpath(os.path.expanduser(tmpexc_item))
          if os.path.isdir(exc_item):
            os.write(exlist_tmpfile, '- ' + exc_item + '/*\n')
          else:
            os.write(exlist_tmpfile, '- ' + exc_item + '\n')
        os.close(exlist_tmpfile)
        self.log.logger.debug('Exclude file: %s', self.exlist_tmpname)
    except AttributeError, e:
      self.log.logger.warning('%s', e)

  def BackupEntry(self):
    """Sync each source entries and backup partition (destination).

    Performs the initial sequential backup process. For each entry in the list
    enlist (entries mentioned in config file), backup process is run to sync
    the source and destination (backup partition)
    """

    if self.backupmethod == "RSYNC":
      self.ssh_shell_var = [self.ssh_path, self.sshport,
                       self.sshuser, self.backupserver]
    else:
      self.ssh_shell_var = None

    for entry in self.enlist:
      # Print appropriate messsages and perform an initial full backup.
      startbackup = backup.Backup(self.backupdirpath,
                                  self.rsync_path,
                                  self.exlist_tmpname,
                                  entry, log_handle=self.log,
                                  dryrun=self.log.dryrun,
                                  sh_var=self.ssh_shell_var)
      startbackup.VerifyBackup()

  def CreateServerThread(self):
    """Create the server daemon.

    This function forks the main thread into background and tries to
    become a daemon. Also stops logging to console and thus have no controlling
    terminal. Becomes daemon only if variable nofork is False (-F option in
    command line argumment). Also gets ready to receive following signals:
    SIGINT, SIGQUIT, SIGTERM and SIGUSR1 (raised in StartAsyncBackupThread).
    Finally, after becoming a daemon, invokes BackupServer function to start
    timer threads and filesystem monitoring.

    Ref: http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/278731
    for details on how to create a daemon.
    """

    if not self.log.nofork:
      workdir = '/'
      try:
        pid = os.fork()  # First child
      except OSError, e:
        self.log.logger.error('%s', e)
      if pid == 0:
        os.setsid()
        try:
          pid = os.fork()  # Second Child
        except OSError, e:
          self.log.logger.error('%s', e)
        if pid == 0:
          self.log.logger.warning('Forking to background. Logs in %s',
                                  self.log.logfilename)
          self.log.logger.info('PID: %s, PPID %s', os.getpid(), os.getppid())
          self.log.logger.removeHandler(self.log.console)
          self.log.console.close()
          os.chdir(workdir)
        else:
          os._exit(0)
      else:
        os._exit(0)

    signal.signal(signal.SIGINT, self.Cleanup)
    signal.signal(signal.SIGQUIT, self.Cleanup)
    signal.signal(signal.SIGTERM, self.Cleanup)
    signal.signal(signal.SIGUSR1, self.Cleanup)

    self.kill_counter = 0
    self.cur_accumlator = 0
    self.prev_accumlator = 0
    self.max_idlecount = 3
    self.idlecount = 0
    self.asyncthreads = []

    self.BackupServer()

  def BackupServer(self):
    """Goes into infinite loop and performs backup, when required.

    BackupServer does the process of starting two timer threads, the trigger
    timer and the entry deletor timer. Trigger (backup) timer thread sleeps for
    timeout_value (syncinterval) seconds and then wakes up to invoke function
    TriggerBackup, while entry deletor timer thread sleeps for
    delthread_starttime seconds and wakes up to invoke StartDeletor function.
    The entry deletor timer is enabled only if retainbackup is False (this
    can be set/unset in the config file, is not enabled if backup mehtod is
    specified as RSYNC). The entry deletor thread is disabled if its no longer
    required (No more files/directories to be removed).

    The main thread goes into an infinite loop watching file system changes.
    This is done by invoking function FileMonStart, followed by checking and
    reading events happening in the monitored file(s)/directories. Main thread
    exits if starting of file monitoring fails.
    """

    self.timeout_value = self.syncinterval      # Global
    self.max_accumlator = self.commitchanges    # Global
    self.maxbackupthreads = 3                   # Global
    self.accumlator = 0
    self.alivecount_gl = 0
    # Time after which app will kill itself, if backups continue to fail.
    self.cutoff_counter = (10 * self.timeout_value)
    self.delthread_starttime = self.timeout_value
    if self.log.debug:
      self.DebugInfo()
      pass
    # Init trigger (backup) timer
    self.trigger = threading.Timer(self.timeout_value, self.TriggerBackup)
    # Init and start entry deletor timer
    if not self.retainbackup:
      self.log.logger.debug('Entry deletor trigger thread going to sleep.')
      self.deltrigger = threading.Timer(self.delthread_starttime,
                                        self.StartDeletor)
      self.deltrigger.start()
    # Start filesystem monitoring
    self.notifier_handle, self.processor_handle = self.FileMonStart()
    if self.notifier_handle:
      while True:
        if not self.trigger.isAlive():
          self.log.logger.debug('Backup trigger thread going to sleep.')
          self.trigger = threading.Timer(self.timeout_value, self.TriggerBackup)
          self.trigger.start()
        if not self.retainbackup:
          if not self.log.deletor_disable:
            if not self.deltrigger.isAlive():
              self.log.logger.debug('Entry deletor trigger thread going to'
                                    ' sleep.')
              self.deltrigger = threading.Timer(self.delthread_starttime,
                                                self.StartDeletor)
              self.deltrigger.start()
          else:
            if self.deltrigger.isAlive():
              self.log.logger.warning('Disable entry deletor trigger thread.')
              self.deltrigger.cancel()
        try:
          # Filesystem changes are checked and read here
          self.notifier_handle.process_events()
          if self.notifier_handle.check_events():
            self.notifier_handle.read_events()
        except KeyboardInterrupt:
          self.log.logger.warning('Stop file monitoring.')
          self.notifier_handle.stop()
          self.log.logger.warning('Stop timer thread.')
          if self.trigger.isAlive():
            self.trigger.cancel()
          break
        except Exception, strerr:
          print strerr
    else:
      msg = ('Failed to start file monitoring')
      self.log.logger.critical(msg)
      if not self.noguihelper:
        self.gui_helperpid = None
        self.ShowGuiMsg(msg, self.log.myname)
        os.waitpid(self.gui_helperpid, os.WUNTRACED)
      sys.exit(1)

  def FileMonStart(self):
    """This function starts the file monitoring.

    Monitoring starts for every valid path mentioned in list enlist. Monitoring
    is done either recursively or non-recursively, depending on the recursive
    field of that entry. Uses class FileMonEventProcessor for processing the
    events that occur in the monitored files/directories.

    Returns:
      event_notifier: Object - to the Notifying system
      event_processor: Object - to class FileMonEventProcessor, which processes
        the events occuring in filesystem
    """

    avail_events = pyinotify.EventsCodes
    # Events to be monitored.
    eventsmonitored = (avail_events.IN_CLOSE_WRITE | avail_events.IN_CREATE |
                       avail_events.IN_DELETE | avail_events.IN_MODIFY |
                       avail_events.IN_MOVED_FROM | avail_events.IN_MOVED_TO |
                       avail_events.IN_ATTRIB | avail_events.IN_MOVE_SELF)
    # Start a event watcher
    event_watcher = pyinotify.WatchManager()
    # Create a event processor
    event_processor = FileMonEventProcessor()
    # Read change notifications and process events accordingly
    event_notifier = pyinotify.Notifier(event_watcher, event_processor)
    for item in self.enlist:
      if item['recursive']:
        event_watcher.add_watch(item['path'], eventsmonitored, rec=True,
                                auto_add=True)
        self.log.logger.info('Start monitoring of %s [recursive]'
                             % (item['path']))
      else:
        # Add path to be watched for filesystem changes
        event_watcher.add_watch(item['path'], eventsmonitored)
        self.log.logger.info('Start monitoring of %s', item['path'])
    return event_notifier, event_processor

  def TriggerBackup(self):
    """Triggers backup if required.

    Function is responsible for determining whether its required to perform a
    backup operation. This is done by looking at the variable accumlator, which
    is a counter keeping track of file/directory modification events. If there
    are indeed changes to be backed up, function StartAsyncBackupThread is
    called. Calls function ShowResources if log.showresources is True (-R
    option in command line)

    This function is invoked every time timer thread wakes up after sleeping
    for syncinterval seconds.
    """

    self.accumlator = self.processor_handle.counter
    self.paths_modified = self.processor_handle.changed_path
    self.log.logger.debug('Backup trigger thread finished sleeping and wokeup.')
    self.log.logger.debug('Paths modified %s, Accumlated changes: %s'
                          % (self.paths_modified, self.accumlator))
    if self.accumlator >= self.max_accumlator:
      self.log.logger.info('Flushing %s accumlated changes to backup dir',
                           self.accumlator)
      self.StartAsyncBackupThread()
    elif self.accumlator:
      self.prev_accumlator = self.cur_accumlator
      self.cur_accumlator = self.accumlator
      if self.cur_accumlator == self.prev_accumlator:
        self.idlecount += 1
      else:
        self.idlecount = 0
      if self.idlecount >= self.max_idlecount:
        self.log.logger.info('Idle filesystem, Flush all changes (%s)'
                             ' accumlated till now', self.accumlator)
        self.StartAsyncBackupThread()
    if self.log.showresources:
      self.ShowResources()

  def StartAsyncBackupThread(self):
    """Create new thread for backup.

    Start a separate thread which will perform backup of the modfied entry. How
    it works is described below:
      - Checks whether the backup partition is still mounted (available for
      backups, if backup method is NFS).
        - If not, then performing a backup is impossible (level ERROR). Popup a
          GUI message box to the user and continue file monitoring. If the
          number of attempts to backup fail because the backup partition is
          unavailable, then issue a self-kill signal and exit.
      - If yes (backup partition available), then make sure the number of
      active threads are less than the maximum permitted limit
      (maxbackupthreads) and initiate a backup by starting the backup thread.
        - If the maxmum threads are already active, then continue monitoring
          the filesystem and don't start the backup thread. Instead, increase
          the timeout (syncinterval) value and wait for active number of
          threads to be less than the maximum permitted limit.
      - When backup method is specified as RSYNC, there is no check done to
        verify whether the remote end is available or not. The daemon will
        print error messages and continue to perform rsync for ever. (Unlike
        when backup method is NFS, where the daemon gives up and exits after
        repeated failures.)
    Responsible for showing the GUI popup message box if backup partition is not
    available for backup. Removes the message box (if already active), if backup
    partition is available again.
    """

    if not self.IsBackupPartitionMounted():
      alivecount = 0
      for item in self.asyncthreads:
        if item.isAlive():
          alivecount += 1
        else:
          self.asyncthreads.remove(item)
        self.alivecount_gl = alivecount
      if alivecount >= self.maxbackupthreads:
        # Increase timeout (syncinterval) to give some time for the existing
        # active threads to finish their execution.
        self.log.logger.warning('Maximum number (%s) of threads already'
                                ' running', alivecount)
        self.timeout_value += (self.timeout_value/2)
        self.log.logger.warning('Increased "syncinterval" to %s',
                                self.timeout_value)
      else:
        if not os.path.exists(self.exlist_tmpname):
          self.log.logger.warning('Can\'t find exclude file created'
                                  ' earlier: %s', self.exlist_tmpname)
          self.log.logger.warning('Trying to create exclude file again')
          self.CreateExclude()
        asyncbackup = backup.AsyncBackup(self.backupdirpath,
                                         self.rsync_path,
                                         self.exlist_tmpname,
                                         self.enlist,
                                         self.paths_modified,
                                         self.log,
                                         sh_var=self.ssh_shell_var)
        asyncbackup.start()
        # Reset everything to start afresh, now that we've started a new
        # thread to do backup.
        self.asyncthreads.append(asyncbackup)
        self.processor_handle.counter = 0
        self.processor_handle.changed_path = []
        self.cur_accumlator = 0
        self.prev_accumlator = 0
        self.idlecount = 0
        self.kill_counter = 0
        if alivecount:
          self.log.logger.debug('Active threads: %s', alivecount)
        # Reduce the timeout (syncinterval) if all seems fine.
        if self.timeout_value > self.syncinterval:
          self.timeout_value -= (self.timeout_value/2)
          if self.timeout_value < self.syncinterval:
            self.timeout_value = self.syncinterval
            self.log.logger.info('Re-setting "syncinterval" to %s',
                                 self.timeout_value)
          else:
            self.log.logger.info('Reduced "syncinterval" to %s',
                                 self.timeout_value)
      self.RemGuiMsg()
      if not self.log.internal_disable:
        self.log.deletor_disable = False
    else:
      # Backup partition not available. Print message to console/file and also
      # show a GUI message box to inform user.
      self.PartitionUnavail()
      self.log.deletor_disable = True
    self.kill_counter += self.syncinterval

  def PartitionUnavail(self):
    msg = "Won't be able to perform backup."
    self.log.logger.critical(msg)
    guimsg = msg
    #NFS
    if self.backupmethod == "NFS":
      msg="Looks like NFS mount is unavailable."
      self.log.logger.critical(msg)
      guimsg = guimsg + '\n' + msg
      if self.MountPartition():
        msg = ('Remount failed. You will have to manually mount the NFS'
               'parition.\n Mount "%s":"%s" to localmount "%s"',
               self.methlist[0], self.methlist[1], self.methlist[2])
        self.log.logger.warning(msg)
        guimsg = guimsg + '\n' + msg
      else:
        msg = 'However, remount was a success.'
        self.log.logger.warning(msg)
        guimsg = guimsg + '\n' + msg
    # Show Message
    if not self.noguihelper:
      self.ShowGuiMsg(guimsg, self.log.myname)
    if self.kill_counter >= self.cutoff_counter:
      msg = ('Failed to perform backup for pretty long time. '
             'Quitting! Please investigate.')
      self.log.logger.critical(msg)
      guimsg = guimsg + '\n' + msg
      if not self.noguihelper:
        self.ShowGuiMsg(guimsg, self.log.myname)
      # Kill self if we've been running for long long time, unable to perform
      # a backup.
      os.kill(os.getpid(), signal.SIGUSR1)

  def StartDeletor(self):
    """Starts the thread which removes un-needed files/directories.

    Starts the deletor thread, which does the cleaning up operation of the
    backup drive. Cleaning up is nothing but removing those files which are
    not part of the backup schedule (and older than retentiontime defined in
    the config file). The operation is done in a separate thread called the
    deletor thread. The deletor thread is started here. StartDeletor function
    is invoked by the Timer thread after sleeping for a period of time. The
    delthread_starttime variable is doubled everytime, since the deletor thread
    is a resource hungry one (as it searches in the backup partition for
    file/directories recursively.) Deletion operation is not supported when
    backup method is RSYNC.
    """

    if not self.log.deletor_disable:
      deletor_thread = deletor.EntryDeletor(self.backupdirpath,
                                            self.enlist, self.retentiontime,
                                            self.log,
                                            show_files=self.log.showdelfiles)
      if not deletor_thread.isAlive():
        self.log.logger.debug('Starting unscheduled entry deletor thread')
        deletor_thread.start()
      else:
        self.log.logger.debug('Unscheduled entry deletor thread is already'
                              ' active')
      if self.delthread_starttime <= self.retentiontime:
        self.delthread_starttime += self.delthread_starttime
    else:
      if self.deltrigger.isAlive():
        self.log.logger.warning('(Start)Disable entry deletor trigger thread.')
        self.deltrigger.cancel()

  def ShowGuiMsg(self, msg, title):
    """Display message box for level ERROR messages.

    Show a GUI pop-up message to user, indicating them that something bad
    (level ERROR) has happened. Currently this is used when backups fail. Uses
    external program "zenity" to show the message. Must be replaced by 
    python-gtk (TODO)

    Args:
      msg: String - message to be displayed
      title: String - title of the message box
    """

    try:
      pid, status = os.waitpid(self.gui_helperpid, os.WNOHANG)
      if pid == self.gui_helperpid:
        self.gui_helperpid = os.spawnlp(os.P_NOWAIT, self.gui_helper,
                                        self.gui_helper, '--error', '--text',
                                        msg, '--title', title)
    except (OSError, TypeError):
      self.gui_helperpid = os.spawnlp(os.P_NOWAIT, self.gui_helper,
                                      self.gui_helper, '--error', '--text', msg,
                                      '--title', title)

  def RemGuiMsg(self):
    """Remove message box if not required.

    Remove the GUI popup message if it is active. This is required when the
    previous condition (level ERROR) that caused the GUI popup message no
    longer exists. This function causes an automatic removal of the GUI popup
    message box and cleans up zombies. Must be replaced by python-gtk (TODO)
    """

    if self.gui_helperpid:
      try:
        pid, status = os.waitpid(self.gui_helperpid, os.WNOHANG)
      except OSError:
        pass
      if not pid == self.gui_helperpid:
        try:
          os.kill(self.gui_helperpid, signal.SIGTERM)
          pid, status = os.waitpid(self.gui_helperpid, os.WUNTRACED)
        except OSError:
          pass
      try:
        pid, status = os.waitpid(self.gui_helperpid, os.WNOHANG)
      except OSError:
        pass
      self.gui_helperpid = None

  def Cleanup(self, signo, stkframe):
    """Perform a clean exit.

    Responsible for performing all the cleanup operations when the application
    exits. The application can exit owing to an handled/unhandled exception
    or after receiving a SIGINT, SIGQUIT, SIGTERM or SIGUSR1 signals. This
    function tries to close all open descriptors, remove the exclude file
    created in CreateExclude function, try to sync any pending filesystem
    changes if possible, stop the file monitoring timer thread, stop the
    deletor timer thread and shutdown logging system.

    Filesystem changes are synced to backup partition only under following
    conditions are met:
      - Variable accumlator has a non-zero value
      - The received signal is either of SIGINT, SIGQUIT, SIGTERM  and not
        SIGUSR1 or SIGKILL
      - Backup partition is still mounted (available for backup)
      - Maximum number of threads active are less than value of
        maxbackupthreads

    Args:
      signo: Integer - Signal number recieved by the application which
        resulted in calling this function.
      stkframe: Interrupted stack frame
    """

    self.log.logger.critical('Oops! Got signal %s', signo)
    # If any GUI popup messages are active, kill it, because we're exiting.
    self.RemGuiMsg()
    if self.accumlator:
      if not self.IsBackupPartitionMounted():
        if not signo == signal.SIGUSR1:
          if not self.alivecount_gl >= self.maxbackupthreads:
            self.log.logger.warning('Please wait while syncing pending changes'
                                    ' to backup partition')
            # Try to backup the pending changes
            self.StartAsyncBackupThread()
            for item in self.asyncthreads:
              if item.isAlive():
                item.join()
          else:
            self.log.logger.warning('Maximum number (%s) of threads already'
                                    ' running', self.alivecount_gl)
            self.log.logger.warning('There are pending changes, and it is'
                                    'possible that backup threads are running.'
                                    'But not performing backup and quitting'
                                    ' now.')
        else:
          self.log.logger.warning('There are pending changes, but not syncing'
                                  ' since we\'re self-terminating')
      else:
        self.log.logger.warning('There are pending changes, but not performing'
                                ' backup.')
    try:
      # Remove temporary exclude file
      os.remove(self.exlist_tmpname)
    except OSError, e:
      self.log.logger.error('%s', e)
      self.log.logger.error('Failed to remove temporary exclude file.')
    self.log.logger.warning('Removed temporary exclude file.')
    self.log.logger.warning('Stop file monitoring.')
    try:
      # Stop file monitoring
      self.notifier_handle.stop()
    except AttributeError, e:
      self.log.logger.warning('File monitoring not yet started.')
    self.log.logger.warning('Stop backup trigger thread.')
    if self.trigger.isAlive():
      # Stop timer thread
      self.trigger.cancel()
    if not self.retainbackup:
      self.log.logger.warning('Stop entry deletor trigger thread.')
      if self.deltrigger.isAlive():
        # Stop timer thread
        self.deltrigger.cancel()
    self.log.logger.warning('Stop logging and quit!')
    # Stop logging
    self.log.LogStop()
    os._exit(0)

  def ShowResources(self):
    """Print resource usage in DEBUG mode."""

    rsrce_self = resource.getrusage(resource.RUSAGE_SELF)
    self.log.logger.debug('Resource usage (self), PID: %d', os.getpid())
    self.log.logger.debug('%s: %s', 'Time in user mode', rsrce_self[0])
    self.log.logger.debug('%s: %s', 'Time in system mode', rsrce_self[1])
    resrce_type = ['SleepAVG', 'State', 'VmPeak', 'VmSize', 'VmRSS',
                   'VmData', 'VmExe', 'VmStk', 'VmExe', 'VmLib', 'Threads',
                   'FDSize']
    stat = file('/proc/self/status', 'r')
    stat_r = stat.read()
    stat.close()
    for rsrce in resrce_type:
      try:
        msg = (stat_r[stat_r.index(rsrce):].split('\n', 3)[0])
        self.log.logger.debug(msg)
      except ValueError:
        pass
    del stat_r

  def DebugInfo(self):
    """Print some debug information in DEBUG mode."""

    self.log.logger.debug('Rsync binary path = %s', self.rsync_path)
    self.log.logger.debug('Sync interval = %s', self.glist[1])
    self.log.logger.debug('Commit changes = %s', self.glist[2])
    self.log.logger.debug('Maintain backup files = %s', self.glist[6])
    self.log.logger.debug('Retain backups = %s', self.glist[5])
    self.log.logger.debug('Retention time = %s', self.glist[4])
    self.log.logger.debug('Exclude list = %s', self.exclist)
    self.log.logger.debug('Entry list = %s', self.enlist)
    self.log.logger.debug('Cutoff counter = %s', self.cutoff_counter)
    self.log.logger.debug('Delete Timer time = %s', self.delthread_starttime)
    self.log.logger.debug('Max backup threads = %s', self.maxbackupthreads)

    self.log.logger.debug('Backup method = %s', self.glist[0])
    if self.backupmethod == "NFS":
      self.log.logger.debug('Server = %s', self.methlist[0])
      self.log.logger.debug('Remote mount = %s', self.methlist[1])
      self.log.logger.debug('Local mount = %s', self.methlist[2])
      if self.nfsoptions:
        self.log.logger.debug('NFS options = %s', self.nfsoptions)
    elif self.backupmethod == "RSYNC":
      self.log.logger.debug('Server = %s', self.methlist[0])
      self.log.logger.debug('Remote path = %s', self.methlist[1])
      if self.sshport:
        self.log.logger.debug('SSH port = %s', self.sshport)
    elif self.backupmethod == "LOCAL":
      self.log.logger.debug('Local mount = %s', self.methlist[2])



class FileMonEventProcessor(pyinotify.ProcessEvent):
  """This class does the file event processing.

  This class get invoked by the pyinotify Notifier, whenever a monitored
  event (FileMonStart.eventsmonitored) occurs. The method process_default is
  performs the necessary actions.
  """

  def __init__(self):
    self.counter = 0
    self.changed_path = []

  def process_default(self, event):
    """Gets invoked for every event being monitored.

    Increments counter and keeps track of the modified list. This function
    is invoked whenever an event being monitored (eventsmonitored) from
    FileMonStart occurs.

    Args:
      event: Event Object
    """

    self.counter += 1
    modpath = event.path
    try:
      self.changed_path.index(modpath)
    except ValueError:
      self.changed_path.append(modpath)

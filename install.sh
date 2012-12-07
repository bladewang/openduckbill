#!/bin/bash

# Author : Anoop Chandran <anoopj@google.com>
# A basic (dirty) installer 

PROG=`basename $0`
APP="openduckbill"
SRCDIR="./src"
DOCSDIR="./docs"
CONF_SRCDIR="./conf"

if [ -z $1 ]; then
  echo "Usage: $PROG </path/to/install_directory>"
  echo "Example: $PROG /usr/local/openduckbill"
  exit 1
fi

if [ ! -e "$1" ]; then
  echo "$PROG: Directory '$1' does not exist!"
  echo "    Please create directory '$1' before starting"
  exit 1
fi

DESTDIR=$1

if [ ! -d $SRCDIR ]; then
  echo "$PROG: Cannot find source directory: $SRCDIR"
  echo "    Please run this command from the root directory of '$APP' package"
  exit 1
fi

if [ ! -d $CONF_SRCDIR ]; then
  echo "$PROG: Cannot find config directory: $CONF_SRCDIR"
  echo "    Please run this command from the root directory of '$APP' package"
  exit 1
fi

INSTALL_PGM=`which install`
if [ $? -ne 0 ]; then
  INSTALL_PGM="cp"
  USE_CP=True
fi

echo "$PROG: Start file copy/install."
echo
let stat=0

$INSTALL_PGM -v $SRCDIR/backup.py $DESTDIR || let stat+=1
$INSTALL_PGM -v $SRCDIR/daemon.py $DESTDIR || let stat+=1
$INSTALL_PGM -v $SRCDIR/deletor.py $DESTDIR || let stat+=1
$INSTALL_PGM -v $SRCDIR/helper.py $DESTDIR || let stat+=1
$INSTALL_PGM -v $SRCDIR/__init__.py $DESTDIR || let stat+=1
$INSTALL_PGM -v $SRCDIR/init.py $DESTDIR || let stat+=1
$INSTALL_PGM -v $SRCDIR/logger.py $DESTDIR || let stat+=1
$INSTALL_PGM -v $SRCDIR/openduckbilld.py $DESTDIR || let stat+=1
$INSTALL_PGM -v $DOCSDIR/README $DESTDIR || let stat+=1
$INSTALL_PGM -v $DOCSDIR/README.access $DESTDIR || let stat+=1

if [ $stat -gt 0 ]; then
  echo
  echo "$PROG: Install commands seems to have failed."
  exit 1
else
  if [ $USE_CP ]; then
    echo 
    echo "$PROG: Fixing permissions"
    chmod 0755 $DESTDIR/*.py
  fi
  echo
  echo "$PROG: Install to $DESTDIR was success"
fi

if [ "$USER" == "root" ]; then
  CONFIG_USER=$SUDO_USER
  if [ ! $CONFIG_USER ]; then
    CONFIG_USER=$USER
  fi
  RUNNING_AS_ROOT=True
else
  CONFIG_USER=$USER
  RUNNING_AS_ROOT=False
fi

if [ $CONFIG_USER == "root" ]; then
  CONFIG_HOME="/root"
else
  CONFIG_HOME="/home/$CONFIG_USER"
fi
CONFIG_DIR="$CONFIG_HOME/.openduckbill"

if [ ! -e "${CONFIG_DIR}" ]; then
  mkdir $CONFIG_DIR
fi

if [ -e "${CONFIG_DIR}/config.yaml" ]; then
  SAVETIME=`date +%F-%T`
  echo 
  echo "$PROG: Doing backup of old config file."
  cp -v ${CONFIG_DIR}/config.yaml ${CONFIG_DIR}/config.yaml.save-${SAVETIME}
fi

$INSTALL_PGM -v ${CONF_SRCDIR}/config.yaml ${CONFIG_DIR}/config.yaml
CONFIG_USERGRP=`id -g ${CONFIG_USER}`
chown ${CONFIG_USER}:${CONFIG_USERGRP} ${CONFIG_DIR}/
chown ${CONFIG_USER}:${CONFIG_USERGRP} ${CONFIG_DIR}/config.yaml*

if [ $RUNNING_AS_ROOT ]; then
  echo
  echo "$PROG: Creating symlink /usr/bin/openduckbill"
  ln -svf $DESTDIR/openduckbilld.py /usr/bin/openduckbill
else
  echo
  echo "$PROG: You might want to create a symbolic link from '$DESTDIR/openduckbilld.py' to '/usr/bin/openduckbill'"
  echo "$PROG: Run following command as root"
  echo "    ln -sf $DESTDIR/openduckbilld.py /usr/bin/openduckbill"
fi

echo
echo "$PROG: Installation complete."
echo
echo "NOTE: You might also need to install 'pyinotify' (http://pyinotify.sourceforge.net/)"
echo "      and 'PyYAML' (http://pyyaml.org/wiki/PyYAML), if you haven't done so yet."
echo "      Please go through $DESTDIR/README on how to use '$APP'"

exit 0

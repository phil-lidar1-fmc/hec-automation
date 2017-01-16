#!/usr/bin/env bash

GIT='/cygdrive/c/Program Files/Git/bin/git.exe'
INSTALL_PATH='/cygdrive/c/hec-automation'

echo
echo Fixing git config...
"$GIT" config --global core.autocrlf false

echo
echo Pulling latest code from branch...
out=$( "$GIT" pull origin prod_v2 )
echo "$out" | grep 'Updating'
if [ $? -eq 0 ]; then
    echo Update found...

    echo Reinstalling requirements...
    /cygdrive/c/Python27/Scripts/pip.exe install -r requirements.txt

    echo Restarting script...
    exec "$INSTALL_PATH/run.sh"
fi

echo
echo Running multiple models in 1 VM...
/cygdrive/c/Python27/python.exe -u "$INSTALL_PATH/run.py"

#!/usr/bin/env bash

echo
echo Fixing git config...
'/cygdrive/c/Program Files/Git/bin/git.exe' config --global core.autocrlf input

echo
echo Pulling latest code from branch...
out=$( '/cygdrive/c/Program Files/Git/bin/git.exe' pull origin prod_v2 )
echo "$out" | grep 'Updating'
if [ $? -eq 0 ]; then
    echo Update found...

    echo Reinstalling requirements...
    /cygdrive/c/Python27/Scripts/pip.exe install -r requirements.txt

    echo Restarting script...
    exec 'run.sh'
fi

echo
echo Running multiple models in 1 VM...
/cygdrive/c/Python27/python.exe -u run.py

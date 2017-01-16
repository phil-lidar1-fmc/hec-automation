@echo off

set GIT=C:\Program Files\Git\bin\git.exe

echo.
echo Fixing git config...
"%GIT%" config --global core.autocrlf false

echo.
echo Pulling latest code from branch...
"%GIT%" pull origin prod_v2

echo.
echo Reinstalling requirements...
C:\Python27\Scripts\pip.exe install -r requirements.txt

echo.
echo Running multiple models in 1 VM...
C:\Python27\python.exe -u run.py

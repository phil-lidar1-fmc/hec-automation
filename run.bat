@echo off

echo.
echo Fixing git config...
C:\Program Files\Git\bin\git.exe config --global core.autocrlf false

echo.
echo Running run.sh...
set PATH=C:\cygwin64\bin;%PATH%
C:\cygwin64\bin\bash.exe run.sh

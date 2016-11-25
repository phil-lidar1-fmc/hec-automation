@echo off

set PYTHON_EXE_PATH=C:\Python27\python.exe

echo.
echo Pulling latest code from branch
"C:\Program Files\Git\bin\git.exe" pull origin prod_v2

echo.
echo Running multiple models in 1 VM...
"%PYTHON_EXE_PATH%" -u run.py

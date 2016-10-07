@echo off

set INSTALL_PATH=C:\hec-automation
set PYTHON_EXE_PATH=C:\Python27\python.exe
set HEC_TOOLS_PATH=%INSTALL_PATH%\hec_tools
set PYTHONPATH=%INSTALL_PATH%\hec_tools;%INSTALL_PATH%\dss_handler

echo.
echo Emptying temporary directories...
del /q/f/s %TEMP%\*

echo.
echo Starting main_control.py...
"%PYTHON_EXE_PATH%" -u "%HEC_TOOLS_PATH%\main_control.py"  %*

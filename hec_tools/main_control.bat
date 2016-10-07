@echo off

rem set INSTALL_PATH=C:\Documents and Settings\hmsrasauto-admin\My Documents\Dropbox
set INSTALL_PATH=Z:\
set PYTHON_EXE_PATH=C:\Python27\python.exe
set HEC_TOOLS_PATH=%INSTALL_PATH%\hec_tools
set PYTHONPATH=%INSTALL_PATH%\hec_tools;%INSTALL_PATH%\dss_handler

echo.
echo Emptying temporary directories...
set CWD=%cd%
call "%INSTALL_PATH%\temp_cleanup.bat"
cd %CWD%

echo.
echo Starting main_control.py...
"%PYTHON_EXE_PATH%" -u "%HEC_TOOLS_PATH%\main_control.py"  %*
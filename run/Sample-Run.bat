@echo off

set BIN=C:\hec-automation\hec_tools
set CONF=C:\hec-automation\conf

echo Running automation system...
call "%BIN%\main_control.bat" "%CONF%\CDO.conf"

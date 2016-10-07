@echo off
set INSTALL_PATH=C:\Documents and Settings\hmsrasauto-admin\My Documents\Dropbox
set JAVA_PATH=C:\Documents and Settings\hmsrasauto-admin\My Documents\Dropbox\jre1.8.0
set HEC_DSSVUE_PATH=C:\Program Files\HEC\HEC-DSSVue
set JYTHON_PATH=C:\jython2.7b2
set DSS_HANDLER_PATH=%INSTALL_PATH%\dss_handler

::cd "%DSS_HANDLER_PATH%"

set CLASS_PATH=%JYTHON_PATH%\jython.jar
set CLASS_PATH=%CLASS_PATH%;%JYTHON_PATH%\Lib
set CLASS_PATH=%CLASS_PATH%;%JYTHON_PATH%\Lib\site-packages
set CLASS_PATH=%CLASS_PATH%;%INSTALL_PATH%\dss_handler
set CLASS_PATH=%CLASS_PATH%;%INSTALL_PATH%\hec_tools
set CLASS_PATH=%CLASS_PATH%;%HEC_DSSVUE_PATH%\jar\sys\codebase.jar
set CLASS_PATH=%CLASS_PATH%;%HEC_DSSVUE_PATH%\jar\sys\jai_codec.jar
set CLASS_PATH=%CLASS_PATH%;%HEC_DSSVUE_PATH%\jar\sys\jai_core.jar
set CLASS_PATH=%CLASS_PATH%;%HEC_DSSVUE_PATH%\jar\sys\jai_imageio.jar
set CLASS_PATH=%CLASS_PATH%;%HEC_DSSVUE_PATH%\jar\sys\jcommon.jar
set CLASS_PATH=%CLASS_PATH%;%HEC_DSSVUE_PATH%\jar\sys\jdom.jar
set CLASS_PATH=%CLASS_PATH%;%HEC_DSSVUE_PATH%\jar\sys\jfreechart.jar
set CLASS_PATH=%CLASS_PATH%;%HEC_DSSVUE_PATH%\jar\sys\jh.jar
set CLASS_PATH=%CLASS_PATH%;%HEC_DSSVUE_PATH%\jar\sys\jxl.jar
set CLASS_PATH=%CLASS_PATH%;%HEC_DSSVUE_PATH%\jar\sys\jython.jar
set CLASS_PATH=%CLASS_PATH%;%HEC_DSSVUE_PATH%\jar\sys\jythonlib.jar
set CLASS_PATH=%CLASS_PATH%;%HEC_DSSVUE_PATH%\jar\sys\jythonUtils.jar
set CLASS_PATH=%CLASS_PATH%;%HEC_DSSVUE_PATH%\jar\gridUtil.jar
set CLASS_PATH=%CLASS_PATH%;%HEC_DSSVUE_PATH%\jar\hec.jar
set CLASS_PATH=%CLASS_PATH%;%HEC_DSSVUE_PATH%\jar\hecData.jar
set CLASS_PATH=%CLASS_PATH%;%HEC_DSSVUE_PATH%\jar\heclib.jar
set CLASS_PATH=%CLASS_PATH%;%HEC_DSSVUE_PATH%\jar\images.jar
set CLASS_PATH=%CLASS_PATH%;%HEC_DSSVUE_PATH%\jar\rma.jar
set CLASS_PATH=%CLASS_PATH%;%JAVA_PATH%\lib\resources.jar
set CLASS_PATH=%CLASS_PATH%;%JAVA_PATH%\lib\rt.jar
set CLASS_PATH=%CLASS_PATH%;%JAVA_PATH%\lib\jsse.jar
set CLASS_PATH=%CLASS_PATH%;%JAVA_PATH%\lib\jce.jar
set CLASS_PATH=%CLASS_PATH%;%JAVA_PATH%\lib\charsets.jar
set CLASS_PATH=%CLASS_PATH%;%JAVA_PATH%\lib\jfr.jar
set CLASS_PATH=%CLASS_PATH%;%JAVA_PATH%\lib\ext\access-bridge-32.jar
set CLASS_PATH=%CLASS_PATH%;%JAVA_PATH%\lib\ext\dnsns.jar
set CLASS_PATH=%CLASS_PATH%;%JAVA_PATH%\lib\ext\jaccess.jar
set CLASS_PATH=%CLASS_PATH%;%JAVA_PATH%\lib\ext\localedata.jar
set CLASS_PATH=%CLASS_PATH%;%JAVA_PATH%\lib\ext\sunec.jar
set CLASS_PATH=%CLASS_PATH%;%JAVA_PATH%\lib\ext\sunjce_provider.jar
set CLASS_PATH=%CLASS_PATH%;%JAVA_PATH%\lib\ext\sunmscapi.jar
set CLASS_PATH=%CLASS_PATH%;%JAVA_PATH%\lib\ext\sunpkcs11.jar
set CLASS_PATH=%CLASS_PATH%;%JAVA_PATH%\lib\ext\zipfs.jar

"%JAVA_PATH%\bin\java.exe" -classpath "%CLASS_PATH%" "-Dpython.path=%CLASS_PATH%" "-Djava.library.path=%HEC_DSSVUE_PATH%\lib"  -Xms512m -Xmx1024m org.python.util.jython "%DSS_HANDLER_PATH%\dss_handler.py" %*
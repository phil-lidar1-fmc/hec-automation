'''
Copyright (c) 2013, Kenneth Langga (klangga@gmail.com)
All rights reserved.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

from asti_sensor import ASTISensor
from datetime import datetime, timedelta
from pprint import pprint, pformat
import argparse
import collections
import hechms_control
import hecras_control
import logging.handlers
import math
import numpy.random
import os
import subprocess
import sys
import time

_logger = logging.getLogger()
_LOG_LEVEL = logging.DEBUG
_CONS_LOG_LEVEL = logging.INFO
_FILE_LOG_LEVEL = logging.DEBUG
_MAIN_CONFIG = None
_HECHMS_CONFIG = None
_HECRAS_CONFIG = None

# Add required binaries default paths to PATH environment variable
default_paths = ['C:\\OSGeo4W64\\bin',
                 'C:\\cygwin64\\bin']
os.environ['PATH'] = (os.pathsep.join(default_paths) +
                      os.pathsep + os.environ['PATH'])

MainConfig = collections.namedtuple('MainConfig',
                                    ['install_dir',
                                     'java_dir',
                                     'hecdssvue_dir',
                                     'hechms_dir',
                                     'hechms_cmd',
                                     'hecras_exe',
                                     'ogr2ogr_exe',
                                     'p7z_exe',
                                     'jython_dir',
                                     'charts_dir',
                                     'json_dir',
                                     'interval',
                                     'testing',
                                     'start_time',
                                     'end_time',
                                     'run_once',
                                     'run_hechms',
                                     'run_hecras'])
HECHMSConfig = collections.namedtuple('HECHMSConfig',
                                      ['hechms_proj_dir',
                                       'hechms_proj_name',
                                       'ctrl_specs',
                                       'ts_data',
                                       'comp_script',
                                       'disc_dss_file_path',
                                       'disc_gages',
                                       'prec_gages'])
HECRASConfig = collections.namedtuple('HECRASConfig',
                                      ['hecras_proj_dir',
                                       'hecras_proj_file',
                                       'flood_map_dir',
                                       'kml_place_name',
                                       'kmz_output_dir',
                                       'plan_file',
                                       'unsflow_file',
                                       'smooth_algo',
                                       'doug_peuc_tol',
                                       'sma_sample_size'])


def _setup_logging(args):

    # Setup logging
    _logger.setLevel(_LOG_LEVEL)
#    formatter = logging.Formatter('[%(asctime)s] %(filename)s: %(message)s')
    formatter = logging.Formatter('[%(asctime)s] %(filename)s \
(%(levelname)s,%(lineno)d)\t: %(message)s')

    global _CONS_LOG_LEVEL
    if args.verbose >= 1:
        _CONS_LOG_LEVEL = logging.DEBUG
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(_CONS_LOG_LEVEL)
    ch.setFormatter(formatter)
    _logger.addHandler(ch)

    fh = logging.FileHandler(os.path.join('log', 'main_control.log'), mode='w')
    fh.setLevel(_FILE_LOG_LEVEL)
    fh.setFormatter(formatter)
    _logger.addHandler(fh)


def _parse_arguments():

    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='count')
    parser.add_argument('conf_file')
    args = parser.parse_args()
    return args


def _get_conf(conf_file):

    # Check first if conf file exists
    _logger.info('Checking if conf file exists...')
    conf_path = os.path.abspath(conf_file)
    is_exists(conf_path)

    # Read conf file
    _logger.info('Reading conf file...')
    conf = {}
    section = None
    disc_gage = None
    with open(conf_path, 'r') as open_file:
        for line in open_file:
            if not line.startswith('#') and not line.isspace():

                if '[ General' in line:
                    section = 'General'
                elif '[ Run' in line:
                    section = 'Run'
                elif '[ HEC-HMS' in line:
                    section = 'HEC-HMS'
                elif '[ HEC-RAS' in line:
                    section = 'HEC-RAS'
                    disc_gage = line.strip()[1:-1].split(' - ')[1].strip()

                if section and section not in conf:
                    conf[section] = {}
                if section == 'HEC-RAS' and disc_gage not in conf[section]:
                    conf[section][disc_gage] = {}

                tokens = line.strip().split('=')
                if len(tokens) > 1:
                    var = tokens[0]
                    if ';' in tokens[1]:
                        val = [t
                               for t in tokens[1].split(';')
                               if t != '']
                    else:
                        val = tokens[1]

                    if section:
                        if section != 'HEC-RAS':
                            conf[section][var] = val
                        else:
                            conf[section][disc_gage][var] = val

    # for k, v in sorted(conf.items()):
    #     _logger.debug('%s: %s', k, v)

    # pprint(conf)

    _logger.debug('conf: %s', pformat(conf, width=40))

    # Parsing general and run configuration
    _general_and_run_conf(conf)

    if _MAIN_CONFIG.run_hechms:

        # Parsing hechms configuration
        _hechms_conf(conf)

        if _MAIN_CONFIG.run_hecras:

            global _HECRAS_CONFIG
            _HECRAS_CONFIG = {}

            for disc_gage in _HECHMS_CONFIG.disc_gages.viewkeys():

                if disc_gage in conf['HEC-RAS']:
                    # Parsing hecras configuration
                    _hecras_conf(disc_gage, conf['HEC-RAS'][disc_gage])
                    # exit(1)

            _logger.info('_HECRAS_CONFIG: %s', pformat(_HECRAS_CONFIG))

    # exit(1)


def _check_conf(conf, conf_keys):
    missing_conf = False
    for conf_key in conf_keys:
        if not conf_key in conf:
            _logger.error('%s missing in conf file!', conf_key)
            missing_conf = True
    if missing_conf:
        exit(1)


def _general_and_run_conf(conf):

    _logger.info('Checking if General and Run section of conf file is \
complete...')

    # General ###
    _logger.info('### General ###')

    _check_conf(conf['General'],
                ['HEC-DSSVueDir', 'HEC-HMSDir',
                 'HEC-RASDir', 'OSGeo4W64Dir', '7-ZipDir', 'JythonDir'])

    # Get install directory path and check if it exists
    _logger.info('Getting install directory path and checking if it exists...')
    # install_dir = os.path.abspath(conf['InstallDir'])
    hectools_dir = os.path.split(os.path.abspath(__file__))[0]
    install_dir = os.path.split(hectools_dir)[0]
    is_exists(install_dir)
    _logger.debug('install_dir: %s', install_dir)

    # Get java home directory path and check if it exists
    _logger.info('Getting java home directory path and checking if it \
exists...')
    # java_dir = os.path.abspath(conf['JavaDir'])
    java_dir = os.path.join(install_dir, 'jre1.8.0')
    is_exists(java_dir)
    _logger.debug('java_dir: %s', java_dir)

    # Get HEC-DSSVue install directory path and check if it exists
    _logger.info('Getting HEC-DSSVue install directory path and checking if \
it exists...')
    hecdssvue_dir = os.path.abspath(conf['General']['HEC-DSSVueDir'])
    is_exists(hecdssvue_dir)
    _logger.debug('hecdssvue_dir: %s', hecdssvue_dir)

    # Get HEC-HMS install directory path and check if it exists
    _logger.info('Getting HEC-HMS install directory path and checking if it \
exists...')
    hechms_dir = os.path.abspath(conf['General']['HEC-HMSDir'])
    is_exists(hechms_dir)
    _logger.debug('hechms_dir: %s', hechms_dir)

    # Get HEC-HMS.cmd file path and check if it exists
    _logger.info('Getting HEC-HMS.cmd file path and checking if it exists...')
    hechms_cmd = os.path.abspath(os.path.join(hechms_dir, 'HEC-HMS.cmd'))
    is_exists(hechms_cmd)
    _logger.debug('hechms_cmd: %s', hechms_cmd)

    # Get HEC-RAS install directory path and check if it exists
    _logger.info('Getting HEC-RAS install directory path and checking if it \
exists...')
    hecras_dir = os.path.abspath(conf['General']['HEC-RASDir'])
    is_exists(hecras_dir)
    _logger.debug('hecras_dir: %s', hecras_dir)

    # Get ras.exe file path and check if it exists
    _logger.info('Getting ras.exe file path and checking if it exists...')
    hecras_exe = os.path.abspath(os.path.join(hecras_dir, 'ras.exe'))
    is_exists(hecras_exe)
    _logger.debug('hecras_exe: %s', hecras_exe)

    # Get OSGeo4W64 install directory path and check if it exists
    _logger.info('Getting OSGeo4W64 install directory path and checking it if \
exists...')
    osgeo4w64_dir = os.path.abspath(conf['General']['OSGeo4W64Dir'])
    is_exists(osgeo4w64_dir)
    _logger.debug('osgeo4w64_dir: %s', osgeo4w64_dir)

    # Get ogr2ogr.exe file path and check if it exists
    _logger.debug('Getting ogr2ogr_exe.exe file path and checking if it \
exists...')
    ogr2ogr_exe = os.path.abspath(
        os.path.join(osgeo4w64_dir, 'bin', 'ogr2ogr.exe'))
    is_exists(ogr2ogr_exe)
    _logger.debug('ogr2ogr_exe: %s', ogr2ogr_exe)

    # Get 7-zip install directory path and check if it exists
    _logger.debug('Getting 7-zip install directory path and checking if it \
exists...')
    _7zip_dir = os.path.abspath(conf['General']['7-ZipDir'])
    is_exists(_7zip_dir)
    _logger.debug('_7zip_dir: %s', _7zip_dir)

    # Get 7z.exe file path and check if it exists
    _logger.debug('Getting 7z.exe file path and checking if it exists...')
    _7z_exe = os.path.abspath(os.path.join(_7zip_dir, '7z.exe'))
    is_exists(_7z_exe)
    _logger.debug('_7z_exe: %s', _7z_exe)

    # Get jython install directory path and check if it exists
    _logger.info('Getting jython install directory path and checking if it \
exists...')
    jython_dir = os.path.abspath(conf['General']['JythonDir'])
    is_exists(jython_dir)
    _logger.debug('jython_dir: %s', jython_dir)

    # Get charts output directory path and check if it exists
    _logger.info('Getting charts output directory path and checking if it \
exists...')
    # charts_dir = os.path.abspath(conf['ChartsDir'])
    charts_dir = os.path.join(install_dir, 'charts')
    is_exists(charts_dir)
    _logger.debug('charts_dir: %s', charts_dir)

    # Get json output directory path and check if it exists
    _logger.info('Getting json output directory path and checking if it \
exists')
    # json_dir = os.path.abspath(conf['JSONDir'])
    json_dir = os.path.join(install_dir, 'json')
    is_exists(json_dir)
    _logger.debug('json_dir: %s', json_dir)

    # Run ###
    _logger.info('### Run ###')

    _check_conf(conf['Run'],
                ['Interval', 'Testing', 'RunOnce', 'RunHEC-HMS', 'RunHEC-RAS'])

    # Get run interval
    _logger.info('Getting run interval...')
    try:
        interval = int(conf['Run']['Interval'])
    except ValueError:
        _logger.exception('Error parsing "Interval" from conf file! Exiting.')
        exit(1)
    _logger.debug('interval: %s', interval)

    # Check if testing is enabled
    _logger.info('Checking if testing is enabled...')
    try:
        testing = eval(conf['Run']['Testing'])
    except NameError:
        # if conf['Testing'] == 'True':
        #     testing = True
        # elif conf['Testing'] == 'False':
        #     testing = False
        # else:
        _logger.exception('Error parsing "Testing" from conf file! Exiting.')
        exit(1)
    _logger.debug('testing: %s', testing)

    # # Get start time if is present
    # _logger.info('Getting start time (if it is present)...')
    # if 'StartTime' in conf:

    # Get start and end time if testing is True
    _logger.info('Getting start and end time (if testing is enabled)...')
    start_time = None
    end_time = None
    if testing:
        if not ('StartTime' in conf['Run'] and 'EndTime' in conf['Run']):
            _logger.error('"StartTime" and "EndTime" not present in conf \
file!')
            _logger.error('Exiting.')
            exit(1)
        try:
            start_time = datetime.strptime(
                conf['Run']['StartTime'], '%Y-%m-%d %H:%M')
        except ValueError:
            _logger.error('Error parsing "StartTime" from conf file! Exiting.')
            exit(1)
        _logger.debug('start_time: %s', start_time)
        try:
            end_time = datetime.strptime(
                conf['Run']['EndTime'], '%Y-%m-%d %H:%M')
        except ValueError:
            _logger.error('Error parsing "EndTime" from conf file! Exiting.')
            exit(1)
        _logger.debug('end_time: %s', end_time)

    # Check if run once is enabled
    _logger.info('Checking if run once is enabled...')
    try:
        run_once = eval(conf['Run']['RunOnce'])
    # if conf['RunOnce'] == 'True':
    #     run_once = True
    # elif conf['RunOnce'] == 'False':
    #     run_once = False
    # else:
    except NameError:
        _logger.exception('Error parsing "RunOnce" from conf file! Exiting.')
        exit(1)
    _logger.debug('run_once: %s', run_once)

    # Check if HEC-HMS is going to be run
    _logger.info('Checking if HEC-HMS is going to be run...')
    try:
        run_hechms = eval(conf['Run']['RunHEC-HMS'])
    except NameError:
        # if conf['RunHEC-HMS'] == 'True':
        #     run_hechms = True
        # elif conf['RunHEC-HMS'] == 'False':
        #     run_hechms = False
        # else:
        _logger.exception(
            'Error parsing "RunHEC-HMS" from conf file! Exiting.')
        exit(1)
    _logger.debug('run_hechms: %s', run_hechms)

    # Check if HEC-RAS is going to be run
    _logger.info('Checking if HEC-RAS is going to be run...')
    try:
        run_hecras = eval(conf['Run']['RunHEC-RAS'])
        if run_hecras and not run_hechms:
            # if conf['RunHEC-RAS'] == 'True':
            #     if run_hechms:
            #         run_hecras = True
            #     else:
            _logger.error('"RunHEC-RAS" cannot be enabled if "RunHEC-HMS" is \
disabled! Exiting.')
            exit(1)
    # elif conf['RunHEC-RAS'] == 'False':
    #     run_hecras = False
    # else:
    except NameError:
        _logger.exception(
            'Error parsing "RunHEC-RAS" from conf file! Exiting.')
        exit(1)
    _logger.debug('run_hecras: %s', run_hecras)

    global _MAIN_CONFIG
    _MAIN_CONFIG = MainConfig(install_dir,
                              java_dir,
                              hecdssvue_dir,
                              hechms_dir,
                              hechms_cmd,
                              hecras_exe,
                              ogr2ogr_exe,
                              _7z_exe,
                              jython_dir,
                              charts_dir,
                              json_dir,
                              interval,
                              testing,
                              start_time,
                              end_time,
                              run_once,
                              run_hechms,
                              run_hecras)
    _logger.info('_MAIN_CONFIG: %s', pformat(_MAIN_CONFIG))


def _hechms_conf(conf):
    _logger.info('Checking if HEC-HMS section of conf file is complete...')

    _check_conf(
        conf['HEC-HMS'],
        ['HEC-HMSProjectDir', 'HEC-HMSProjectName', 'PrecipGages',
         'DischargeGages', 'HQ_Curve', 'TidalCorrection', 'PredictSeriesPrio'])

    # HEC-HMS #
    _logger.info('### HEC-HMS ###')

    # Get HEC-HMS project directory path and check if it exists
    _logger.info('Getting HEC-HMS project directory path and check if it \
exists...')
    hechms_proj_dir = os.path.abspath(conf['HEC-HMS']['HEC-HMSProjectDir'])
    is_exists(hechms_proj_dir)
    _logger.debug('hechms_proj_dir: %s', hechms_proj_dir)

    # Get HEC-HMS project name
    _logger.info('Getting HEC-HMS project name...')
    hechms_proj_name = conf['HEC-HMS']['HEC-HMSProjectName']
    _logger.debug('hechms_proj_name: %s', hechms_proj_name)

    # Get control specification file path and check if it exists
    _logger.info('Getting control specification file path and checking if it \
exists...')
    ctrl_specs = os.path.abspath(os.path.join(hechms_proj_dir,
                                              hechms_proj_name + '.control'))
    is_exists(ctrl_specs)
    _logger.debug('ctrl_specs: %s', ctrl_specs)

    # Get time series data file path and check if it exists
    _logger.info('Getting time series data file path and checking if it \
exists...')
    ts_data = os.path.abspath(os.path.join(hechms_proj_dir,
                                           hechms_proj_name + '.gage'))
    is_exists(ts_data)
    _logger.debug('ts_data: %s', ts_data)

    # Get compute script path and check if it exists
    _logger.info('Getting compute script path and checking if it exists...')
    comp_script = os.path.abspath(os.path.join(hechms_proj_dir,
                                               'compute.script'))
    is_exists(comp_script)
    _logger.debug('comp_script: %s', comp_script)

    # Get discharge dss file path and check if it exists
    _logger.info('Getting discharge dss file path and checking if it \
exists...')
    disc_dss_file_path = os.path.abspath(
        os.path.join(hechms_proj_dir,
                     hechms_proj_name + '.dss'))
    is_exists(disc_dss_file_path)
    _logger.debug('disc_dss_file_path: %s', disc_dss_file_path)

    # Get discharge gage information
    _logger.info('Getting discharge gage/s information...')
    disc_gages = {}
    for disc_gage in conf['HEC-HMS']['DischargeGages']:
        _logger.debug('disc_gage: %s', disc_gage)

        # Check if discharge gage info is in the parameters file
        if disc_gage not in conf['HEC-HMS']:
            _logger.error('%s information is missing! Exiting.', disc_gage)
            exit(1)
        _logger.debug("conf['HEC-HMS'][disc_gage]: %s",
                      conf['HEC-HMS'][disc_gage])

        # Get dev id and data type
        try:
            if '|' in conf['HEC-HMS'][disc_gage]:
                tokens = conf['HEC-HMS'][disc_gage].split('|')
                dev_id = int(tokens[0])
                if tokens[1] == 'MSL':
                    data_type = 'waterlevel_msl'
                elif tokens[1] == 'NON-MSL':
                    data_type = 'waterlevel'
                else:
                    _logger.error('Unrecognized option! (tokens: %s)', tokens)
                    _logger.error('Exiting.')
                    exit(1)
            else:
                dev_id = int(conf['HEC-HMS'][disc_gage])
                data_type = 'waterlevel_msl'
        except Exception:
            _logger.exception('Error getting discharge info!')
            _logger.error('Exiting.')
            exit(1)

        disc_gages[disc_gage] = {
            'sensor': ASTISensor(dev_id)
        }
        disc_gages[disc_gage]['sensor'].data_type(data_type)

        # Check if tidal correction is enabled for this gage
        if disc_gage in conf['HEC-HMS']['TidalCorrection']:
            disc_gages[disc_gage]['tidal_correct'] = True
        else:
            disc_gages[disc_gage]['tidal_correct'] = False

        # Initialize water level offset
        disc_gages[disc_gage]['waterlevel_offset'] = 0.

        # Initialize chart options
        disc_gages[disc_gage]['chart_options'] = {
            'forecast_hours': timedelta(hours=12)
        }

    # Get h-q curve eqn info for each discharge gage
    _logger.info('Getting h-q curve eqn info for each discharge gage...')
    try:
        for hq_curve in conf['HEC-HMS']['HQ_Curve']:
            _logger.debug('hq_curve: %s', hq_curve)

            tokens = hq_curve.split('|')
            _logger.debug('tokens: %s', tokens)

            disc_gage = tokens[0]
            _logger.debug('disc_gage: %s', disc_gage)

            hq_curve_a = float(tokens[1])
            _logger.debug("hq_curve_a: %s", hq_curve_a)

            disc_gages[disc_gage]['hq_curve_a'] = float(tokens[1])
            hq_curve_b = float(tokens[2])

            _logger.debug("hq_curve_b: %s", hq_curve_b)
            disc_gages[disc_gage]['hq_curve_b'] = float(tokens[2])

            if tokens[3] == 'LIN':
                disc_gages[disc_gage]['hq_curve_eqn'] = 'LINEAR'
            elif tokens[3] == 'EXP':
                disc_gages[disc_gage]['hq_curve_eqn'] = 'EXPONENTIAL'
            elif tokens[3] == 'POW':
                disc_gages[disc_gage]['hq_curve_eqn'] = 'POWER'
            elif tokens[3] == 'LOG':
                disc_gages[disc_gage]['hq_curve_eqn'] = 'LOGARITHMIC'
            else:
                _logger.error('Invalid h-q curve equation identifier! \
Exiting.')
                exit(1)

        _logger.debug("disc_gages[disc_gage]['hq_curve_eqn']: %s",
                      disc_gages[disc_gage]['hq_curve_eqn'])
    except ValueError:
        _logger.exception('Error parsing "HQ_Curve" from conf file! Exiting.')
        exit(1)

    # Get water level offset for each discharge gage
    _logger.info('Getting water level offset for each discharge gage...')
    if 'WaterLevelOffset' in conf['HEC-HMS']:
        try:
            for offset_info in conf['HEC-HMS']['WaterLevelOffset']:
                tokens = offset_info.split('|')

                disc_gage = tokens[0]
                _logger.debug('disc_gage: %s', tokens[0])

                offset = float(tokens[1])
                _logger.debug('offset: %s', offset)

                disc_gages[disc_gage]['waterlevel_offset'] = offset
        except ValueError:
            _logger.exception(
                'Error parsing "WaterLevelOffset" from conf file! Exiting.')
            exit(1)

    # Get spilling levels for each discharge gage
    _logger.info('Getting spilling levels for each discharge gage...')
    if 'SpillingLevels' in conf['HEC-HMS']:
        try:
            for spilling_levels in conf['HEC-HMS']['SpillingLevels']:

                tokens = spilling_levels.split('|')

                disc_gage = tokens[0]
                _logger.debug('disc_gage: %s', disc_gage)

                l = float(tokens[1])
                _logger.debug('l: %s', l)

                r = float(tokens[2])
                _logger.debug('r: %s', r)

                disc_gages[disc_gage]['spilling_levels'] = {
                    'left_bank': l,
                    'right_bank': r
                }
        except ValueError:
            _logger.exception('Error parsing "SpillingLevels" from conf file! \
Exiting.')
            exit(1)

    # Get chart options for each discharge gage
    _logger.info('Getting chart options for each discharge gage...')
    if 'ChartOptions' in conf['HEC-HMS']:
        try:
            for chart_options in conf['HEC-HMS']['ChartOptions']:

                tokens = chart_options.split('|')

                disc_gage = tokens[0]
                _logger.debug('disc_gage: %s', disc_gage)

                for t in tokens[1:]:
                    k, v = t.split('>')
                    if k == 'FH':
                        disc_gages[disc_gage]['chart_options']\
                            ['forecast_hours'] = timedelta(hours=int(v))
                    elif k == 'MN':
                        disc_gages[disc_gage]['chart_options']\
                            ['min_waterlevel'] = float(v)
                    elif k == 'MX':
                        disc_gages[disc_gage]['chart_options']\
                            ['max_waterlevel'] = float(v)

        except Exception:
            _logger.exception('Error parsing "ChartOptions" from conf file! \
Exiting.')
            exit(1)

        # Get predicted series priority for each discharge gage
    _logger.info('Getting predicted series priority for each discharge \
gage...')
    for pseries_prio in conf['HEC-HMS']['PredictSeriesPrio']:

        tokens = pseries_prio.split('|')
        _logger.debug('tokens[0]: %s', tokens[0])

        disc_gages[tokens[0]]['pseries_prio'] = tokens[1:]
        _logger.debug("disc_gages[tokens[0]]['pseries_prio']: %s",
                      disc_gages[tokens[0]]['pseries_prio'])

    _logger.debug('disc_gages:\n%s', pformat(disc_gages, width=40))

    # Get precipitation gages information
    _logger.info('Getting precipitation gages information...')
    prec_gages = {}
    for prec_gage in conf['HEC-HMS']['PrecipGages']:
        _logger.debug('prec_gage: %s', prec_gage)

        if prec_gage not in conf['HEC-HMS']:
            _logger.error('%s information is missing! Exiting.', prec_gage)
            exit(1)
        _logger.debug("conf['HEC-HMS'][prec_gage]: %s",
                      conf['HEC-HMS'][prec_gage])

        try:
            prec_gages[prec_gage] = {
                'sensor': ASTISensor(int(conf['HEC-HMS'][prec_gage]))
            }
            prec_gages[prec_gage]['sensor'].data_type('rain_value')
        except Exception:
            _logger.exception('Error getting precipitation gage info!')
            _logger.error('Exiting.')
            exit(1)

    _logger.debug('prec_gages:\n%s', pformat(prec_gages, width=40))

    global _HECHMS_CONFIG
    _HECHMS_CONFIG = HECHMSConfig(hechms_proj_dir,
                                  hechms_proj_name,
                                  ctrl_specs,
                                  ts_data,
                                  comp_script,
                                  disc_dss_file_path,
                                  disc_gages,
                                  prec_gages)
    _logger.info('_HECHMS_CONFIG: %s', _HECHMS_CONFIG)
    # _print_namedtuple(_HECHMS_CONFIG)


def _hecras_conf(disc_gage, conf):
    _logger.info('Checking if HEC-RAS section of conf file is complete...')

    _check_conf(conf, ['HEC-RASProjectDir', 'HEC-RASProjectName',
                       'FloodMappingDir', 'KMLPlacemarkName', 'KMZOutputDir',
                       'SmoothingAlgorithm', 'PlanExtension',
                       'UnsteadyFlowExtension'])

    # HEC-RAS ###
    _logger.info('### HEC-RAS ###')

    # Get HEC-RAS project directory path and check if it exists
    _logger.info('Getting HEC-RAS project directory path and checking if it \
exists...')
    hecras_proj_dir = os.path.abspath(conf['HEC-RASProjectDir'])
    is_exists(hecras_proj_dir)
    _logger.debug('hecras_proj_dir: %s', hecras_proj_dir)

    # Get HEC-RAS project name
    _logger.info('Getting HEC-RAS project name...')
    hecras_proj_name = conf['HEC-RASProjectName']
    _logger.debug('hecras_proj_name: %s', hecras_proj_name)

    # Get HEC-RAS project file
    hecras_proj_file = os.path.abspath(os.path.join(hecras_proj_dir,
                                                    hecras_proj_name + '.prj'))
    is_exists(hecras_proj_file)
    _logger.debug('hecras_proj_file: %s', hecras_proj_file)

    # Get flood mapping shapefile directory path and check if it exists
    _logger.info('Getting flood mapping shapefile directory path and checking \
if it exists...')
    flood_map_dir = os.path.abspath(conf['FloodMappingDir'])
    is_exists(flood_map_dir)
    _logger.debug('flood_map_dir: %s', flood_map_dir)

    # Get kml placeholder name
    _logger.info('Getting kml placeholder name...')
    kml_place_name = conf['KMLPlacemarkName']
    _logger.debug('kml_place_name: %s', kml_place_name)

    # Get kmz output directory and check if it exists
    _logger.info('Getting kmz output directory path and checking if it \
exists...')
    kmz_output_dir = os.path.abspath(conf['KMZOutputDir'])
    is_exists(kmz_output_dir)
    _logger.debug('kmz_output_dir: %s', kmz_output_dir)

    # Get plan file
    _logger.info('Getting plan file...')
    plan_file = os.path.abspath(os.path.join(hecras_proj_dir,
                                             hecras_proj_name +
                                             conf['PlanExtension']))
    is_exists(plan_file)
    _logger.debug('plan_file: %s', plan_file)

    # Get unsteady flow file
    _logger.info('Getting unsteady flow file...')
    unsflow_file = os.path.abspath(os.path.join(hecras_proj_dir,
                                                hecras_proj_name +
                                                conf['UnsteadyFlowExtension']))
    is_exists(unsflow_file)
    _logger.debug('unsflow_file: %s', unsflow_file)

    # Get which smoothing algorithm to run
    _logger.info('Getting which smoothing algorithm to run...')
    if conf['SmoothingAlgorithm'] == 'DOP':
        smooth_algo = 'DOP'
    elif conf['SmoothingAlgorithm'] == 'SMA':
        smooth_algo = 'SMA'
    elif conf['SmoothingAlgorithm'] == 'None':
        smooth_algo = None
    else:
        _logger.error('Error parsing "SmoothingAlgorithm" from conf \
file! Exiting.')
        exit(1)
    _logger.debug('smooth_algo: %s', smooth_algo)
    doug_peuc_tol = None
    sma_sample_size = None

    if smooth_algo == 'DOP':
        if not 'Douglas-PeuckerTolerance' in conf:
            _logger.error('Douglas-Peucker is selected as smoothing algorithm \
but "Douglas-PeuckerTolerance" is missing! Exiting.')
            exit(1)
        # Get douglas-peucker algorithm tolerance
        _logger.info('Getting douglas-peucker algorithm tolerance...')
        try:
            doug_peuc_tol = float(conf['Douglas-PeuckerTolerance'])
        except ValueError as e:
            _logger.error('Error parsing "Douglas-PeuckerTolerance" from conf \
    file! Exiting.')
            _logger.exception(e)
            exit(1)
        _logger.debug('doug_peuc_tol: %s', doug_peuc_tol)

    elif smooth_algo == 'SMA':
        if not 'SMASampleSize' in conf:
            _logger.error('Simple Moving Average is selected as smoothing \
algorithm but "SMASampleSize" is missing! Exiting.')
            exit(1)
        # Get simple moving average sample size
        _logger.info('Getting simple moving average sample size...')
        try:
            sma_sample_size = float(conf['SMASampleSize'])
        except ValueError as e:
            _logger.error('Error parsing "SMASampleSize" from conf \
    file! Exiting.')
            _logger.exception(e)
            exit(1)
        _logger.debug('sma_sample_size: %s', sma_sample_size)

    global _HECRAS_CONFIG
    _HECRAS_CONFIG[disc_gage] = HECRASConfig(hecras_proj_dir,
                                             hecras_proj_file,
                                             flood_map_dir,
                                             kml_place_name,
                                             kmz_output_dir,
                                             plan_file,
                                             unsflow_file,
                                             smooth_algo,
                                             doug_peuc_tol,
                                             sma_sample_size)
    # _logger.info('_HECRAS_CONFIG:')
    # _print_namedtuple(_HECRAS_CONFIG)


def discharge2waterlevel(disc_gage_info, discharge):
    # Get hq curve parameters
    hq_curve_a = disc_gage_info['hq_curve_a']
    hq_curve_b = disc_gage_info['hq_curve_b']
    # _logger.debug('hq_curve_a: %s', hq_curve_a)
    # _logger.debug('hq_curve_b: %s', hq_curve_b)
    hq_curve_eqn = disc_gage_info['hq_curve_eqn']

    # Get water level from discharge depending on the equation
    if hq_curve_eqn == 'EXPONENTIAL':
        if discharge == 0.:
            discharge += 1e-9  # 1 mm^3 / s
        waterlevel = math.log(discharge / hq_curve_a) / hq_curve_b
    elif hq_curve_eqn == 'LINEAR':
        # discharge = a * waterlevel + b
        waterlevel = (discharge - hq_curve_b) / hq_curve_a
    elif hq_curve_eqn == 'POWER':
        # discharge = a * waterlevel ^ b
        waterlevel = math.pow(discharge / hq_curve_a,
                              1 / hq_curve_b)
    elif hq_curve_eqn == 'LOGARITHMIC':
        # discharge - a * ln(waterlevel) + b
        waterlevel = math.exp((discharge - hq_curve_b) / hq_curve_a)
    return waterlevel


def waterlevel2discharge(disc_gage_info, waterlevel):
    # Get hq curve parameters
    hq_curve_a = disc_gage_info['hq_curve_a']
    hq_curve_b = disc_gage_info['hq_curve_b']
    # _logger.debug('hq_curve_a: %s', hq_curve_a)
    # _logger.debug('hq_curve_b: %s', hq_curve_b)
    hq_curve_eqn = disc_gage_info['hq_curve_eqn']
    # _logger.debug('hq_curve_a: %s hq_curve_b: %s hq_curve_eqn: %s', hq_curve_a, hq_curve_b, hq_curve_eqn)
    # Get discharge from water level depending on the equation
    if hq_curve_eqn == 'EXPONENTIAL':
        discharge = hq_curve_a * math.exp(hq_curve_b * waterlevel)
    elif hq_curve_eqn == 'LINEAR':
        discharge = hq_curve_a * waterlevel + hq_curve_b
    elif hq_curve_eqn == 'POWER':
        discharge = hq_curve_a * (waterlevel ** hq_curve_b)
    elif hq_curve_eqn == 'LOGARITHMIC':
        discharge = hq_curve_a * math.log(waterlevel) - hq_curve_b
    return discharge


def is_exists(path):
    if not os.path.exists(path):
        _logger.error('%s does not exist! Exiting.', path)
        exit(1)


def text_file_line_gen(csv_file):
    with open(csv_file, 'r') as opened_file:
        line_number = 1
        for line in opened_file:
            yield line_number, line.strip()
            line_number += 1


def _verify_dss_handler_bat():
    # Check if dss_handler.bat file is valid
    # Get dss handler directory path and check if it exists
    _logger.info('Getting dss handler directory and checking if it exists...')
    dss_handler_dir = os.path.join(_MAIN_CONFIG.install_dir, 'dss_handler')
    is_exists(dss_handler_dir)
    _logger.debug('dss_handler_dir: %s', dss_handler_dir)
    # Get dss_handler.bat file path and check if it exists
    _logger.info('Getting dss_handler.bat file path and checking if it \
exists...')
    dss_handler_bat = os.path.join(dss_handler_dir, 'dss_handler.bat')
    is_exists(dss_handler_bat)
    _logger.info('dss_handler_bat: %s', dss_handler_bat)
    # Read current dss_handler.bat file
    _logger.info('Reading current dss_handler.bat file...')
    new_file = False
    buf = []
    for _, line in text_file_line_gen(dss_handler_bat):
        if not line.startswith('rem'):
            tokens = line.split('=')
            if ('INSTALL_PATH=' in line and
                    _MAIN_CONFIG.install_dir != os.path.abspath(tokens[-1])):
                new_file = True
                buf.append('set INSTALL_PATH=' + _MAIN_CONFIG.install_dir)
                continue
            elif ('JAVA_PATH=' in line and
                  _MAIN_CONFIG.java_dir != os.path.abspath(tokens[-1])):
                new_file = True
                buf.append('set JAVA_PATH=' + _MAIN_CONFIG.java_dir)
                continue
            elif ('HEC_DSSVUE_PATH=' in line and
                  _MAIN_CONFIG.hecdssvue_dir != os.path.abspath(tokens[-1])):
                new_file = True
                buf.append('set HEC_DSSVUE_PATH=' +
                           _MAIN_CONFIG.hecdssvue_dir)
                continue
            elif ('JYTHON_PATH=' in line and
                  _MAIN_CONFIG.jython_dir != os.path.abspath(tokens[-1])):
                new_file = True
                buf.append('set JYTHON_PATH=' + _MAIN_CONFIG.jython_dir)
                continue
        buf.append(line)
    # Write new dss_handler.bat file if needed
    _logger.info('Writing new dss_handler.bat file (if needed)...')
    if new_file:
        with open(dss_handler_bat, 'w') as open_file:
            open_file.write('\n'.join(buf))


def _get_last_current_time(start_time):
    last_minute = (_MAIN_CONFIG.interval *
                   (start_time.minute / _MAIN_CONFIG.interval))
    current_time = datetime(start_time.year,
                            start_time.month,
                            start_time.day,
                            start_time.hour,
                            last_minute)
    return current_time

if __name__ == '__main__':

    # Parse arguments
    _logger.info('Parsing arguments...')
    args = _parse_arguments()

    # Setup logging
    _setup_logging(args)

    # Get configuration from conf file
    _logger.info('Getting configuration from file...')
    _get_conf(args.conf_file)

    # Check if dss_handler.bat file is valid
    _logger.info('Checking if dss_handler.bat file is valid...')
    _verify_dss_handler_bat()

    # Set start time
    if _MAIN_CONFIG.start_time:
        # If start time is not None, set it as current time, even if testing
        # is enabled
        start_time = _MAIN_CONFIG.start_time
    else:
        # Else, set current time to real world current time
        start_time = datetime.now()

    _logger.info('start_time: %s', start_time)
    current_time = _get_last_current_time(start_time)
    _logger.info('current_time: %s', current_time)
    _logger.info('-' * 40)

    # Run main loop
    while (not _MAIN_CONFIG.testing or
           (current_time <= _MAIN_CONFIG.end_time and _MAIN_CONFIG.testing)):

        current_time = _get_last_current_time(start_time)
        _logger.info('current_time: %s', current_time)

        try:

            if _MAIN_CONFIG.run_hechms:
                # Run hechms_control
                hechms_control.hechms_control(current_time,
                                              _MAIN_CONFIG,
                                              _HECHMS_CONFIG)

            # exit(1)

            if _MAIN_CONFIG.run_hecras:
                # Run hecras_control for each exported dss file
                # for base_series, series_info in exported_dss.items():
                #     _logger.info('Running HEC-RAS for: %s', base_series)
                #     hecras_control.hecras_control(current_time,
                #                                   _MAIN_CONFIG,
                #                                   _HECRAS_CONFIG,
                #                                   series_info)
                #     # Currently, there is only a need to run one HEC-RAS
                #     # model per HEC-HMS, so breaking it here
                #     break

                for disc_gage, disc_gage_info in _HECHMS_CONFIG.disc_gages.viewitems():
                    _logger.info('Running HEC-RAS for: %s', disc_gage)
                    hecras_control.hecras_control(_MAIN_CONFIG,
                                                  disc_gage_info,
                                                  _HECRAS_CONFIG[disc_gage])

        except Exception:
            _logger.exception('Error running hechms/hecras!')
            _logger.error('Trying again in the next iteration.')

        # Rsync output to website
        try:
            _logger.info('Rsyncing output to website server...')
            install_dir_unix = '/cygdrive/' + \
                _MAIN_CONFIG.install_dir.replace(
                    '\\', '/').replace('C:', 'c') + '/'
            subprocess.check_call(['rsync.exe', '-rtiPS', install_dir_unix +
                                   'charts/*.html',
                                   'admin@website.dmz.dream.upd.edu.\
ph:/srv/www/www.dream.upd.edu.ph/hectools/charts/'],
                                  shell=True)
            subprocess.check_call(['rsync.exe', '-rtiPS', install_dir_unix +
                                   'json/*.json',
                                   'admin@website.dmz.dream.upd.edu.\
ph:/srv/www/www.dream.upd.edu.ph/hectools/json/'],
                                  shell=True)
            subprocess.check_call(['rsync.exe', '-rtiPS', install_dir_unix +
                                   'kmz/',
                                   'admin@website.dmz.dream.upd.edu.\
ph:/srv/www/www.dream.upd.edu.ph/hectools/kmz/'],
                                  shell=True)
        except subprocess.CalledProcessError:
            import traceback
            traceback.print_exc()

        # If run once is enabled break immediately
        if _MAIN_CONFIG.run_once:
            _logger.info('Run once enabled! Breaking loop.')
            break

        # Increment/wait for the next interval
        # Check times and sleep if needed until the next interval
        if not _MAIN_CONFIG.testing:
            end_time = datetime.now()
            _logger.info('end_time: %s', end_time)
            duration = end_time - start_time
            _logger.info('duration: %s', duration)
            later = start_time + timedelta(minutes=_MAIN_CONFIG.interval)
            if end_time < later:
                sleep_time = (later - end_time).total_seconds()
                _logger.info('Sleeping for %s seconds.', sleep_time)
                time.sleep(sleep_time)
            start_time = datetime.now()
        else:
            start_time += timedelta(minutes=_MAIN_CONFIG.interval)

    # Shutdown logging
    logging.shutdown()

'''
Copyright (c) 2013, Kenneth Langga (klangga@gmail.com)
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
'''

from datetime import datetime, timedelta
import argparse
import collections
import hechms_control
import hecras_control
import logging.handlers
import math
import numpy.random
import os
import os.path as op
import repo_handler
import subprocess
import sys
import time

_version = '2.23'
print(os.path.basename(__file__) + ': v' + _version)
_logger = logging.getLogger()
_LOG_LEVEL = logging.DEBUG
_CONS_LOG_LEVEL = logging.INFO
_FILE_LOG_LEVEL = logging.DEBUG
_MAIN_CONFIG = None
_HECHMS_CONFIG = None
_HECRAS_CONFIG = None
# _MAX_ERRORS = 30
_cur_errors = 0

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
                                     'cache_dir',
                                     'charts_dir',
                                     'json_dir',
                                     'proxy',
                                     'interval',
                                     'normal_interval',
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
                                       'reflect_mins',
                                       'rainfall_scenarios',
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
    fh = logging.handlers.RotatingFileHandler(op.join('log', 'main_control.log'),
                                              maxBytes=1048576, backupCount=5)
    fh.setLevel(_FILE_LOG_LEVEL)
    fh.setFormatter(formatter)
    _logger.addHandler(fh)


def _parse_arguments():
    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', action='version',
                        version=_version)
    parser.add_argument('-v', '--verbose', action='count')
    parser.add_argument('conf_file')
    args = parser.parse_args()
    return args


def _get_conf(conf_file):
    # Check first if conf file exists
    _logger.info('Checking if conf file exists...')
    conf_path = op.realpath(conf_file)
    is_exists(conf_path)
    # Read conf file
    _logger.info('Reading conf file...')
    conf = {}
    with open(conf_path, 'r') as open_file:
        for line in open_file:
            if not line.startswith('#') and not line.isspace():
                tokens = line.strip().split('=')
                if len(tokens) > 1:
                    if ';' in tokens[1]:
                        conf[tokens[0]] = [t for t in tokens[1].split(';')
                                           if t != '']
                    else:
                        conf[tokens[0]] = tokens[1]
    for k, v in sorted(conf.items()):
        _logger.debug('%s: %s', k, v)
    # Parsing general and run configuration
    _general_and_run_conf(conf)
    if _MAIN_CONFIG.run_hechms:
        # Parsing hechms configuration
        _hechms_conf(conf)
        if _MAIN_CONFIG.run_hecras:
            # Parsing hecras configuration
            _hecras_conf(conf)


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
    _check_conf(conf, ['InstallDir', 'JavaDir', 'HEC-DSSVueDir', 'HEC-HMSDir',
                       'HEC-RASDir', 'FWToolsDir', '7-ZipDir', 'JythonDir',
                       'CacheDir', 'ChartsDir', 'JSONDir',
                       'Interval', 'NormalInterval', 'Testing', 'RunOnce',
                       'RunHEC-HMS', 'RunHEC-RAS'])
    # General ###
    # Check if the various directories exist and set as global variables
    _logger.info('### General ###')
    # Get install directory path and check if it exists
    _logger.info('Getting install directory path and checking if it exists...')
    install_dir = op.realpath(conf['InstallDir'])
    is_exists(install_dir)
    _logger.debug('install_dir = %s', install_dir)
    # Get java home directory path and check if it exists
    _logger.info('Getting java home directory path and checking if it \
exists...')
    java_dir = op.realpath(conf['JavaDir'])
    is_exists(java_dir)
    _logger.debug('java_dir = %s', java_dir)
    # Get HEC-DSSVue install directory path and check if it exists
    _logger.info('Getting HEC-DSSVue install directory path and checking if \
it exists...')
    hecdssvue_dir = op.realpath(conf['HEC-DSSVueDir'])
    is_exists(hecdssvue_dir)
    _logger.debug('hecdssvue_dir = %s', hecdssvue_dir)
    # Get HEC-HMS install directory path and check if it exists
    _logger.info('Getting HEC-HMS install directory path and checking if it \
exists...')
    hechms_dir = op.realpath(conf['HEC-HMSDir'])
    is_exists(hechms_dir)
    _logger.debug('hechms_dir = %s', hechms_dir)
    # Get HEC-HMS.cmd file path and check if it exists
    _logger.info('Getting HEC-HMS.cmd file path and checking if it exists...')
    hechms_cmd = op.realpath(op.join(hechms_dir, 'HEC-HMS.cmd'))
    is_exists(hechms_cmd)
    _logger.debug('hechms_cmd = %s', hechms_cmd)
    # Get HEC-RAS install directory path and check if it exists
    _logger.info('Getting HEC-RAS install directory path and checking if it \
exists...')
    hecras_dir = op.realpath(conf['HEC-RASDir'])
    is_exists(hecras_dir)
    _logger.debug('hecras_dir = %s', hecras_dir)
    # Get ras.exe file path and check if it exists
    _logger.info('Getting ras.exe file path and checking if it exists...')
    hecras_exe = op.realpath(op.join(hecras_dir, 'ras.exe'))
    is_exists(hecras_exe)
    _logger.debug('hecras_exe = %s', hecras_exe)
    # Get FWTools install directory path and check if it exists
    _logger.info('Getting FWTools install directory path and checking it if \
exists...')
    fwtools_dir = op.realpath(conf['FWToolsDir'])
    is_exists(fwtools_dir)
    _logger.debug('fwtools_dir = %s', fwtools_dir)
    # Get ogr2ogr.exe file path and check if it exists
    _logger.debug('Getting ogr2ogr_exe.exe file path and checking if it \
exists...')
    ogr2ogr_exe = op.realpath(op.join(fwtools_dir, 'bin', 'ogr2ogr.exe'))
    is_exists(ogr2ogr_exe)
    _logger.debug('ogr2ogr_exe = %s', ogr2ogr_exe)
    # Get 7-zip install directory path and check if it exists
    _logger.debug('Getting 7-zip install directory path and checking if it \
exists...')
    _7zip_dir = op.realpath(conf['7-ZipDir'])
    is_exists(_7zip_dir)
    _logger.debug('_7zip_dir = %s', _7zip_dir)
    # Get 7z.exe file path and check if it exists
    _logger.debug('Getting 7z.exe file path and checking if it exists...')
    _7z_exe = op.realpath(op.join(_7zip_dir, '7z.exe'))
    is_exists(_7z_exe)
    _logger.debug('_7z_exe = %s', _7z_exe)
    # Get jython install directory path and check if it exists
    _logger.info('Getting jython install directory path and checking if it \
exists...')
    jython_dir = op.realpath(conf['JythonDir'])
    is_exists(jython_dir)
    _logger.debug('jython_dir = %s', jython_dir)
    # Get repo cache directory path and check if it exists
    _logger.info('Getting repo cache directory path and checking if it \
exists...')
    cache_dir = op.realpath(conf['CacheDir'])
    is_exists(cache_dir)
    _logger.debug('cache_dir = %s', cache_dir)
    # Get charts output directory path and check if it exists
    _logger.info('Getting charts output directory path and checking if it \
exists...')
    charts_dir = op.realpath(conf['ChartsDir'])
    is_exists(charts_dir)
    _logger.debug('charts_dir = %s', charts_dir)
    # Get json output directory path and check if it exists
    _logger.info('Getting json output directory path and checking if it \
exists')
    json_dir = op.realpath(conf['JSONDir'])
    is_exists(json_dir)
    _logger.debug('json_dir = %s', json_dir)
    # Get proxy if present
    _logger.info('Getting proxy (if it is present)...')
    if 'Proxy' in conf:
        proxy = {'http': conf['Proxy']}
    else:
        proxy = None
    _logger.debug('proxy = %s', proxy)
    # Run ###
    _logger.info('### Run ###')
    # Get run interval
    _logger.info('Getting run interval...')
    try:
        interval = int(conf['Interval'])
    except ValueError as e:
        _logger.error('Error parsing "Interval" from conf file! Exiting.')
        _logger.exception(e)
        exit(1)
    _logger.debug('interval = %s', interval)
    # Check if normal interval is enabled
    _logger.info('Checking if normal interval is enabled...')
    if conf['NormalInterval'] == 'True':
        normal_interval = True
    elif conf['NormalInterval'] == 'False':
        normal_interval = False
    else:
        _logger.error('Error parsing "NormalInterval" from conf file! \
Exiting.')
        exit(1)
    _logger.debug('normal_interval = %s', normal_interval)
    # Check if testing is enabled
    _logger.info('Checking if testing is enabled...')
    if conf['Testing'] == 'True':
        testing = True
    elif conf['Testing'] == 'False':
        testing = False
    else:
        _logger.error('Error parsing "Testing" from conf file! Exiting.')
        exit(1)
    _logger.debug('testing = %s', testing)
    # Get start time if is present
    _logger.info('Getting start time (if it is present)...')
    start_time = None
    if 'StartTime' in conf:
        try:
            start_time = datetime.strptime(conf['StartTime'], '%Y-%m-%d %H:%M')
        except ValueError:
            _logger.error('Error parsing "StartTime" from conf file! Exiting.')
            exit(1)
        _logger.warning('start_time = %s', start_time)
    # Get end time if testing is True
    _logger.info('Getting end time (if testing is enabled)...')
    end_time = None
    if testing:
        if not ('StartTime' in conf and 'EndTime' in conf):
            _logger.error('"StartTime" and "EndTime" not present in conf \
file!')
            _logger.error('Exiting.')
            exit(1)
        try:
            end_time = datetime.strptime(conf['EndTime'], '%Y-%m-%d %H:%M')
        except ValueError:
            _logger.error('Error parsing "EndTime" from conf file! Exiting.')
            exit(1)
        _logger.warning('end_time = %s', end_time)
    # Check if run once is enabled
    _logger.info('Checking if run once is enabled...')
    if conf['RunOnce'] == 'True':
        run_once = True
    elif conf['RunOnce'] == 'False':
        run_once = False
    else:
        _logger.error('Error parsing "RunOnce" from conf file! Exiting.')
        exit(1)
    _logger.debug('run_once = %s', run_once)
    # Check if HEC-HMS is going to be run
    _logger.info('Checking if HEC-HMS is going to be run...')
    if conf['RunHEC-HMS'] == 'True':
        run_hechms = True
    elif conf['RunHEC-HMS'] == 'False':
        run_hechms = False
    else:
        _logger.error('Error parsing "RunHEC-HMS" from conf file! Exiting.')
        exit(1)
    _logger.debug('run_hechms = %s', run_hechms)
    # Check if HEC-RAS is going to be run
    _logger.info('Checking if HEC-RAS is going to be run...')
    if conf['RunHEC-RAS'] == 'True':
        if run_hechms:
            run_hecras = True
        else:
            _logger.error('"RunHEC-RAS" cannot be enabled if "RunHEC-HMS" is \
disabled! Exiting.')
            exit(1)
    elif conf['RunHEC-RAS'] == 'False':
        run_hecras = False
    else:
        _logger.error('Error parsing "RunHEC-RAS" from conf file! Exiting.')
        exit(1)
    _logger.debug('run_hecras = %s', run_hecras)
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
                              cache_dir,
                              charts_dir,
                              json_dir,
                              proxy,
                              interval,
                              normal_interval,
                              testing,
                              start_time,
                              end_time,
                              run_once,
                              run_hechms,
                              run_hecras)
    _logger.info('_MAIN_CONFIG:')
    _print_namedtuple(_MAIN_CONFIG)


def _hechms_conf(conf):
    _logger.info('Checking if HEC-HMS section of conf file is complete...')
    _check_conf(
        conf, ['HEC-HMSProjectDir', 'HEC-HMSProjectName', 'PrecipGages',
               'DischargeGages', 'HQ_Curve', 'ComputeScript',
               'RainfallScenarios', 'TidalCorrection',
               'MinMaxWaterLevelChart', 'ReflectMinutes',
               'PredictSeriesPrio'])
    # HEC-HMS ###
    _logger.info('### HEC-HMS ###')
    # Get HEC-HMS project directory path and check if it exists
    _logger.info('Getting HEC-HMS project directory path and check if it \
exists...')
    hechms_proj_dir = op.realpath(conf['HEC-HMSProjectDir'])
    is_exists(hechms_proj_dir)
    _logger.debug('hechms_proj_dir = %s', hechms_proj_dir)
    # Get HEC-HMS project name
    _logger.info('Getting HEC-HMS project name...')
    hechms_proj_name = conf['HEC-HMSProjectName']
    _logger.debug('hechms_proj_name = %s', hechms_proj_name)
    # Get control specification file path and check if it exists
    _logger.info('Getting control specification file path and checking if it \
exists...')
    ctrl_specs = op.realpath(op.join(hechms_proj_dir,
                                     hechms_proj_name + '.control'))
    is_exists(ctrl_specs)
    _logger.debug('ctrl_specs = %s', ctrl_specs)
    # Get time series data file path and check if it exists
    _logger.info('Getting time series data file path and checking if it \
exists...')
    ts_data = op.realpath(op.join(hechms_proj_dir,
                                  hechms_proj_name + '.gage'))
    is_exists(ts_data)
    _logger.debug('ts_data = %s', ts_data)
    # Get compute script path and check if it exists
    _logger.info('Getting compute script path and checking if it exists...')
    comp_script = op.realpath(op.join(hechms_proj_dir,
                                      conf['ComputeScript']))
    is_exists(comp_script)
    _logger.debug('comp_script = %s', comp_script)
    # Get discharge dss file path and check if it exists
    _logger.info('Getting discharge dss file path and checking if it \
exists...')
    disc_dss_file_path = op.realpath(op.join(hechms_proj_dir,
                                             hechms_proj_name + '.dss'))
    is_exists(disc_dss_file_path)
    _logger.debug('disc_dss_file_path = %s', disc_dss_file_path)
    # Get number of minutes up to the past to reflect rain into the future
    _logger.info('Getting number of minutes up to the past to reflect rain \
into the future...')
    try:
        reflect_mins = int(conf['ReflectMinutes'])
    except ValueError:
        _logger.error('Error parsing "ReflectMinutes" from conf file! \
Exiting.')
        exit(1)
    _logger.debug('reflect_mins = %s', reflect_mins)
    # Get discharge gage information
    _logger.info('Getting discharge gage/s information...')
    disc_gages = collections.OrderedDict()
    for disc_gage in conf['DischargeGages']:
        _logger.debug('disc_gage = %s', disc_gage)
        # Check if discharge gage info is in the parameters file
        if not disc_gage in conf:
            _logger.error('%s information is missing! Exiting.', disc_gage)
            exit(1)
        _logger.debug('conf[disc_gage] = %s', conf[disc_gage])
        # Get repoID from discharge gage info
        try:
            disc_repoID = repo_handler.get_repoID(conf[disc_gage])
        except Exception as e:
            _logger.error(e.message)
            _logger.exception(e)
            _logger.error('Exiting.')
            exit(1)
        disc_gages[disc_gage] = {'repoID': disc_repoID,
                                 'base_series':
                                 repo_handler.id_format(disc_repoID.identifier)}
        _logger.debug('disc_repoID = %s', disc_repoID)
        # Check if tidal correction is enabled for this gage
        if disc_gage in conf['TidalCorrection']:
            disc_gages[disc_gage]['tidal_correct'] = True
        else:
            disc_gages[disc_gage]['tidal_correct'] = False
    # Get water level offset for each discharge gage
    _logger.info('Getting water level offset for each discharge gage...')
    if 'WaterLevelOffset' in conf:
        try:
            for offset_info in conf['WaterLevelOffset']:
                tokens = offset_info.split('|')
                disc_gage = tokens[0]
                _logger.debug('disc_gage = %s', tokens[0])
                offset = float(tokens[1])
                _logger.debug('offset = %s', offset)
                disc_gages[disc_gage]['WaterLevelOffset'] = offset
        except ValueError:
            _logger.error('Error parsing "HQ_Curve" from conf file! Exiting.')
            exit(1)
    else:
        for disc_gage in disc_gages.keys():
            disc_gages[disc_gage]['WaterLevelOffset'] = 0.
    # Get h-q curve eqn info for each discharge gage
    _logger.info('Getting h-q curve eqn info for each discharge gage...')
    try:
        for hq_curve in conf['HQ_Curve']:
            _logger.debug('hq_curve = %s', hq_curve)
            tokens = hq_curve.split('|')
            _logger.debug('tokens = %s', tokens)
            disc_gage = tokens[0]
            _logger.debug('disc_gage = %s', disc_gage)
            hq_curve_a = float(tokens[1])
            _logger.debug("hq_curve_a = %s", hq_curve_a)
            disc_gages[disc_gage]['hq_curve_a'] = float(tokens[1])
            hq_curve_b = float(tokens[2])
            _logger.debug("hq_curve_b = %s", hq_curve_b)
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
        _logger.debug("disc_gages[disc_gage]['hq_curve_eqn'] = %s",
                      disc_gages[disc_gage]['hq_curve_eqn'])
    except ValueError:
        _logger.error('Error parsing "HQ_Curve" from conf file! Exiting.')
        exit(1)
    # Get min/max waterlevel for each discharge gage
    _logger.info('Getting min/max waterlevel for each discharge gage...')
    try:
        for min_max_waterlevel in conf['MinMaxWaterLevelChart']:
            tokens = min_max_waterlevel.split('|')
            _logger.debug('tokens[0] = %s', tokens[0])
            disc_gages[tokens[0]]['min_waterlevel'] = float(tokens[1])
            _logger.debug("disc_gages[tokens[0]]['min_waterlevel'] = %s",
                          disc_gages[tokens[0]]['min_waterlevel'])
            disc_gages[tokens[0]]['max_waterlevel'] = float(tokens[2])
            _logger.debug("disc_gages[tokens[0]]['max_waterlevel'] = %s",
                          disc_gages[tokens[0]]['max_waterlevel'])
    except ValueError:
        _logger.error('Error parsing "MinMaxWaterLevelChart" from conf file! \
Exiting.')
        exit(1)
    # Get predicted series priority for each discharge gage
    _logger.info('Getting predicted series priority for each discharge \
gage...')
    for pseries_prio in conf['PredictSeriesPrio']:
        tokens = pseries_prio.split('|')
        _logger.debug('tokens[0] = %s', tokens[0])
        disc_gages[tokens[0]]['pseries_prio'] = tokens[1:]
        _logger.debug("disc_gages[tokens[0]]['pseries_prio'] = %s",
                      disc_gages[tokens[0]]['pseries_prio'])
    _logger.debug('disc_gages = %s', disc_gages)
    # Get rain scenario file paths and check if they exist
    _logger.info('Getting rain scenarios file paths and checking if they \
exist...')
    rain_scenario_paths = []
    for scene_file in conf['RainfallScenarios']:
        scene_path = op.join(hechms_proj_dir, scene_file)
        is_exists(scene_path)
        rain_scenario_paths.append(scene_path)
    _logger.debug('rain_scenario_paths = %s', rain_scenario_paths)
    # Read rain scenarios from file
    _logger.info('Reading rain scenarios from file...')
    rainfall_scenarios = _read_rain_scenarios(rain_scenario_paths, disc_gages)
    # Get precipitation gages information
    _logger.info('Getting precipitation gages information...')
    prec_gages = {}
    for prec_gage in conf['PrecipGages']:
        _logger.debug('prec_gage = %s', prec_gage)
        if not prec_gage in conf:
            _logger.error('%s information is missing! Exiting.', prec_gage)
            exit(1)
        _logger.debug('conf[prec_gage] = %s', conf[prec_gage])
        try:
            prec_repoID = repo_handler.get_repoID(conf[prec_gage])
        except Exception as e:
            _logger.error(e.message)
            _logger.exception(e)
            _logger.error('Exiting.')
            exit(1)
        prec_gages[prec_gage] = {'repoID': prec_repoID,
                                 'base_series':
                                 repo_handler.id_format(prec_repoID.identifier)}
        _logger.debug('prec_repoID = %s', prec_repoID)
    _logger.debug('prec_gages = %s', prec_gages)
    global _HECHMS_CONFIG
    _HECHMS_CONFIG = HECHMSConfig(hechms_proj_dir,
                                  hechms_proj_name,
                                  ctrl_specs,
                                  ts_data,
                                  comp_script,
                                  disc_dss_file_path,
                                  reflect_mins,
                                  rainfall_scenarios,
                                  disc_gages,
                                  prec_gages)
    _logger.info('_HECHMS_CONFIG:')
    _print_namedtuple(_HECHMS_CONFIG)


def _hecras_conf(conf):
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
    hecras_proj_dir = op.realpath(conf['HEC-RASProjectDir'])
    is_exists(hecras_proj_dir)
    _logger.debug('hecras_proj_dir = %s', hecras_proj_dir)
    # Get HEC-RAS project name
    _logger.info('Getting HEC-RAS project name...')
    hecras_proj_name = conf['HEC-RASProjectName']
    _logger.debug('hecras_proj_name = %s', hecras_proj_name)
    # Get HEC-RAS project file
    hecras_proj_file = op.realpath(op.join(hecras_proj_dir,
                                           hecras_proj_name + '.prj'))
    is_exists(hecras_proj_file)
    _logger.debug('hecras_proj_file = %s', hecras_proj_file)
    # Get flood mapping shapefile directory path and check if it exists
    _logger.info('Getting flood mapping shapefile directory path and checking \
if it exists...')
    flood_map_dir = op.realpath(conf['FloodMappingDir'])
    is_exists(flood_map_dir)
    _logger.debug('flood_map_dir = %s', flood_map_dir)
    # Get kml placeholder name
    _logger.info('Getting kml placeholder name...')
    kml_place_name = conf['KMLPlacemarkName']
    _logger.debug('kml_place_name = %s', kml_place_name)
    # Get kmz output directory and check if it exists
    _logger.info('Getting kmz output directory path and checking if it \
exists...')
    kmz_output_dir = op.realpath(conf['KMZOutputDir'])
    is_exists(kmz_output_dir)
    _logger.debug('kmz_output_dir = %s', kmz_output_dir)
    # Get plan file
    _logger.info('Getting plan file...')
    plan_file = op.realpath(op.join(hecras_proj_dir,
                                    hecras_proj_name + conf['PlanExtension']))
    is_exists(plan_file)
    _logger.debug('plan_file = %s', plan_file)
    # Get unsteady flow file
    _logger.info('Getting unsteady flow file...')
    unsflow_file = op.realpath(op.join(hecras_proj_dir,
                                       hecras_proj_name + conf['UnsteadyFlowExtension']))
    is_exists(unsflow_file)
    _logger.debug('unsflow_file = %s', unsflow_file)
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
    _logger.debug('smooth_algo = %s', smooth_algo)
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
        _logger.debug('doug_peuc_tol = %s', doug_peuc_tol)
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
        _logger.debug('sma_sample_size = %s', sma_sample_size)
    global _HECRAS_CONFIG
    _HECRAS_CONFIG = HECRASConfig(hecras_proj_dir,
                                  hecras_proj_file,
                                  flood_map_dir,
                                  kml_place_name,
                                  kmz_output_dir,
                                  plan_file,
                                  unsflow_file,
                                  smooth_algo,
                                  doug_peuc_tol,
                                  sma_sample_size)
    _logger.info('_HECRAS_CONFIG:')
    _print_namedtuple(_HECRAS_CONFIG)


def _print_namedtuple(aNamedTuple):
    for k, v in aNamedTuple._asdict().items():
        if k != 'rainfall_scenarios':
            _logger.info('%s = %s', k, v)


def _read_rain_scenarios(rain_scenario_paths, disc_gages):
    # Get primary discharge
    disc_gage, _ = disc_gages.items()[0]
    _logger.warn('Primary discharge gage = %s', disc_gage)
    # Read rain scenarios files
    rainfall_scenarios = {}
    for scenario_path in rain_scenario_paths:
        scenario_name = op.splitext(op.basename(scenario_path))[0]
        _logger.debug('scenario_name = %s', scenario_name)
        # Read scenario file
        rainfall_scenarios[scenario_name] = {}
        rainfall_scenarios[scenario_name]['waterlevel'] = {}
        rainfall_scenarios[scenario_name]['rainfall'] = {}
        begin = None
        for lineno, line in text_file_line_gen(scenario_path):
            if lineno > 1:
                tokens = line.split(',')
                # Get time
                time = datetime.strptime(tokens[0], '%Y-%m-%d %H:%M')
                if begin is None:
                    begin = time
                # Get discharge
                discharge = float(tokens[1])
                # Get water level from discharge
                waterlevel = discharge2waterlevel(disc_gages[disc_gage],
                                                  discharge)
                rainfall_scenarios[scenario_name]['waterlevel'][time -
                                                                begin] = waterlevel
                # Get rainfall
                if tokens[2] != '':
                    rainfall = float(tokens[2])
                    rainfall_scenarios[scenario_name]['rainfall'][time -
                                                                  begin] = rainfall
    return rainfall_scenarios


def discharge2waterlevel(disc_gage_info, discharge):
    # Get hq curve parameters
    hq_curve_a = disc_gage_info['hq_curve_a']
    hq_curve_b = disc_gage_info['hq_curve_b']
    hq_curve_eqn = disc_gage_info['hq_curve_eqn']
    # Get water level from discharge depending on the equation
    if hq_curve_eqn == 'EXPONENTIAL':
        # discharge = a * exp(b * waterlevel)
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
    if not op.exists(path):
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
    dss_handler_dir = op.join(_MAIN_CONFIG.install_dir, 'dss_handler')
    is_exists(dss_handler_dir)
    _logger.debug('dss_handler_dir = %s', dss_handler_dir)
    # Get dss_handler.bat file path and check if it exists
    _logger.info('Getting dss_handler.bat file path and checking if it \
exists...')
    dss_handler_bat = op.join(dss_handler_dir, 'dss_handler.bat')
    is_exists(dss_handler_bat)
    _logger.info('dss_handler_bat = %s', dss_handler_bat)
    # Read current dss_handler.bat file
    _logger.info('Reading current dss_handler.bat file...')
    new_file = False
    buf = []
    for _, line in text_file_line_gen(dss_handler_bat):
        if not line.startswith('rem'):
            tokens = line.split('=')
            if ('INSTALL_PATH=' in line and
                    _MAIN_CONFIG.install_dir != op.realpath(tokens[-1])):
                new_file = True
                buf.append('set INSTALL_PATH=' + _MAIN_CONFIG.install_dir)
                continue
            elif ('JAVA_PATH=' in line and
                  _MAIN_CONFIG.java_dir != op.realpath(tokens[-1])):
                new_file = True
                buf.append('set JAVA_PATH=' + _MAIN_CONFIG.java_dir)
                continue
            elif ('HEC_DSSVUE_PATH=' in line and
                  _MAIN_CONFIG.hecdssvue_dir != op.realpath(tokens[-1])):
                new_file = True
                buf.append('set HEC_DSSVUE_PATH=' +
                           _MAIN_CONFIG.hecdssvue_dir)
                continue
            elif ('JYTHON_PATH=' in line and
                  _MAIN_CONFIG.jython_dir != op.realpath(tokens[-1])):
                new_file = True
                buf.append('set JYTHON_PATH=' + _MAIN_CONFIG.jython_dir)
                continue
        buf.append(line)
    # Write new dss_handler.bat file if needed
    _logger.info('Writing new dss_handler.bat file (if needed)...')
    if new_file:
        with open(dss_handler_bat, 'w') as open_file:
            open_file.write('\n'.join(buf))


def _next_interval(current_time):
    _logger.info('Increment/waiting for the next interval')
#    _logger.info('OLD current_time = %s', current_time)
    # If normal interval, force update current time
    if _MAIN_CONFIG.normal_interval:
        current_time = datetime.now()
    _logger.info('current_time = %s', current_time)
    # Get next multiple of interval
    next_minute = (_MAIN_CONFIG.interval *
                   (current_time.minute / _MAIN_CONFIG.interval + 1))
    _logger.debug('next_minute = %s', next_minute)
    delta = timedelta(minutes=(next_minute - current_time.minute))
    _logger.debug('delta = %s', delta)
    next_time = current_time + delta
    next_time = datetime(next_time.year, next_time.month, next_time.day,
                         next_time.hour, next_time.minute)
    _logger.info('next_time = %s', next_time)
    # If normal interval, sleep for <delta> minutes
    if _MAIN_CONFIG.normal_interval:
        _logger.info('datetime.now() = %s', datetime.now())
        sleep_ = next_time - datetime.now()
        if sleep_.total_seconds() > 0:
            _logger.warning('Sleeping for %s secs', sleep_.total_seconds())
            time.sleep(sleep_.total_seconds())
        else:
            # If sleep time is negative, fix next_time to time now
            now = datetime.now()
#            next_time = datetime(now.year, now.month, now.day, now.hour,
#                                 now.minute)
    current_time = next_time
#    _logger.info('NEW current_time = %s', current_time)
    return current_time


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
    _logger.info('start_time = %s', start_time)
    current_time = _get_last_current_time(start_time)
    _logger.info('current_time = %s', current_time)
    _logger.info('-' * 40)
    # Sleep a random amount of time (2-9mins)
    init_sleep = numpy.random.random_integers(2, 18) * 30
    _logger.info('Sleeping for %s secs...', init_sleep)
    # if not _MAIN_CONFIG.testing:
    #    time.sleep(init_sleep)
    # Run main loop
    while (not _MAIN_CONFIG.testing or
           (current_time <= _MAIN_CONFIG.end_time and _MAIN_CONFIG.testing)):
        # while True:
        # Check if current_time's minute is a multiple of interval
        # if current_time.minute % _MAIN_CONFIG.interval != 0:
        #     current_time = _next_interval(current_time)
        _logger.info('#' * 20)
        # start_time = datetime.now()

        # Strip seconds from current time
        # current_time = datetime(current_time.year,
        #                         current_time.month,
        #                         current_time.day,
        #                         current_time.hour,
        #                         current_time.minute)
        current_time = _get_last_current_time(start_time)
        _logger.info('current_time = %s', current_time)
        try:
            # process_start = datetime.now()
            # _logger.info('process_start = %s', process_start)
            # _logger.info('_MAIN_CONFIG.run_hechms = %s',
            # _MAIN_CONFIG.run_hechms)
            if _MAIN_CONFIG.run_hechms:
                # Run hechms_control
                exported_dss = hechms_control.hechms_control(current_time,
                                                             _MAIN_CONFIG,
                                                             _HECHMS_CONFIG)
            # _logger.info('_MAIN_CONFIG.run_hecras = %s',
            # _MAIN_CONFIG.run_hecras)
            if _MAIN_CONFIG.run_hecras:
                # Run hecras_control for each exported dss file
                for base_series, series_info in exported_dss.items():
                    _logger.info('Running HEC-RAS for: %s', base_series)
                    hecras_control.hecras_control(current_time,
                                                  _MAIN_CONFIG,
                                                  _HECRAS_CONFIG,
                                                  series_info)
                    # Currently, there is only a need to run one HEC-RAS
                    # model per HEC-HMS, so breaking it here
                    break
            # process_end = datetime.now()
            # _logger.info('process_end = %s', process_end)
            # _logger.info('process_duration = %s', process_end -
            # process_start)
        except Exception as e:
            _logger.exception(e)
            _logger.error('Trying again in the next iteration.')
        # Rsync output to website
        try:
            _logger.info('Rsyncing output to website server...')
            install_dir_unix = '/cygdrive/' + \
                _MAIN_CONFIG.install_dir.replace(
                    '\\', '/').replace('C:', 'c') + '/'
            subprocess.check_call(['rsync.exe', '-ainPS', install_dir_unix +
                                   'charts/*.html',
                                   'hmsrasauto-admin@website.dmz.dream.upd.edu.\
ph:/srv/www/www.dream.upd.edu.ph/hectools/testing/charts/'],
                                  shell=True)
            subprocess.check_call(['rsync.exe', '-ainPS', install_dir_unix +
                                   'json/*.json',
                                   'hmsrasauto-admin@website.dmz.dream.upd.edu.\
ph:/srv/www/www.dream.upd.edu.ph/hectools/testing/json/'],
                                  shell=True)
            subprocess.check_call(['rsync.exe', '-ainPS', install_dir_unix +
                                   'kmz',
                                   'hmsrasauto-admin@website.dmz.dream.upd.edu.\
ph:/srv/www/www.dream.upd.edu.ph/hectools/testing/kmz/'],
                                  shell=True)
        except subprocess.CalledProcessError:
            import traceback
            traceback.print_exc()
        # If run once is enabled break immediately
        if _MAIN_CONFIG.run_once:
            _logger.info('Run once enabled! Breaking loop.')
            break
        # Increment/wait for the next interval
        # current_time = _next_interval(current_time)
        # Check times and sleep if needed until the next interval
        if not _MAIN_CONFIG.testing:
            end_time = datetime.now()
            _logger.info('end_time = %s', end_time)
            duration = end_time - start_time
            _logger.info('duration = %s', duration)
            later = start_time + timedelta(minutes=_MAIN_CONFIG.interval)
            if end_time < later:
                sleep_time = (later - end_time).total_seconds()
                _logger.info('Sleeping for %s seconds.', sleep_time)
                time.sleep(sleep_time)
            # current_time = datetime.now()
            start_time = datetime.now()
        else:
            # current_time += timedelta(minutes=_MAIN_CONFIG.interval)
            start_time += timedelta(minutes=_MAIN_CONFIG.interval)
    # Shutdown logging
    logging.shutdown()

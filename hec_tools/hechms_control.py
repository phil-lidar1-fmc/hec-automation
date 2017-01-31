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

from datetime import timedelta, datetime
from dss_file import DSSFile
from main_control import discharge2waterlevel, waterlevel2discharge
import collections
import copy
import fractions
import highcharts
import json
import logging
import main_control
import math
import numpy as np
import os
import os.path as op
import pickle
import pprint
import re
import scipy.stats
import subprocess

_version = '2.20'
print(os.path.basename(__file__) + ': v' + _version)
np.seterr(all='raise')
_logger = logging.getLogger()
_SIM_PAST_HOURS = timedelta(hours=36)
_SIM_FUTURE_HOURS = timedelta(hours=24)
_RAIN_PAST_HOURS = timedelta(hours=12)
_HIST_DAYS = timedelta(days=7)
_BF_HT_DIFF = 0.020  # meters
_BF_KERN_SIZE = 7  # samples
_ASERIES = 'Actual'
_PSERIES = 'HEC-HMS'
_POSERIES = _PSERIES + ' + offset'
_PLSERIES = 'HEC-HMS w/ LinearRegress(x-P,y-A)'
_PLOSERIES = _PLSERIES + ' + offset'
_TSERIES = 'Tidal Prediction'
_TOSERIES = _TSERIES + ' + offset'
_PTSERIES = _PSERIES + ' + ' + _TSERIES
_PTOSERIES = _PTSERIES + ' + offset'
_OPSERIES = 'Old Predicted'
_PSERIES_KEYS = [
    _PSERIES, _POSERIES,
    _PLSERIES, _PLOSERIES,
    _TSERIES, _TOSERIES,
    _PTSERIES, _PTOSERIES
]


def hechms_control(current_time, main_config, hechms_config):

    hechms_start = datetime.now()
    _logger.info('hechms_start: %s', hechms_start)

    _logger.info('Initializing...')
    _initialize(current_time, main_config, hechms_config)

    # Get rainfall data in mm
    _logger.info('Getting rainfall data (in mm)...')
    _get_rainfall_data_in_mm()

    # Get rainfall data in mm/hr
    _logger.info('Getting rainfall data (in mm/hr)...')
    _get_rainfall_data_in_mm_per_hr()

    # Get cumulative rainfall
    _logger.info('Getting cumulative rainfall...')
    _get_cumulative_rainfall()

    # Get water level data
    _logger.info('Getting water level data...')
    _get_waterlevel_data()

    # Start simulation
    _logger.info('Starting simulation...')
    _run_hechms()

    # For each discharge gage
    for disc_gage, disc_gage_info in \
            sorted(_HECHMS_CONFIG.disc_gages.viewitems()):

        _logger.info('Discharge gage: %s Location: %s', disc_gage,
                     disc_gage_info['sensor'].meta()['location'])

        # Read HEC-HMS output
        _logger.info('Reading HEC-HMS output...')
        _read_hechms_output(disc_gage, disc_gage_info)

        # Convert discharge to water level
        _logger.info('Converting discharge to water level...')
        _convert_discharge_to_waterlevel(disc_gage_info)

        disc_gage_info['offsets'] = {
            (_PSERIES, _POSERIES): 0.
        }

        # If actual water level data is available
        if disc_gage_info['sensor'].data():

            # Run linear regression on predicted water level
            _logger.info(
                'Running linear regression on predicted water level...')
            try:
                _run_linear_regress_with_outlier_removal(disc_gage_info)
            except Exception:
                _logger.exception('Error running linear regression!')

            # Check if tidal correction is needed
            if disc_gage_info['tidal_correct']:
                _logger.info('Applying tidal correction...')
                _apply_tidal_correction(disc_gage_info)
                disc_gage_info['offsets'][(_TSERIES, _TOSERIES)] = 0.
                disc_gage_info['offsets'][(_PTSERIES, _PTOSERIES)] = 0.

            # Get and apply predicted offsets from actual
            _logger.info('Getting and applying predicted offsets from \
actual...')
            _get_predicted_offset(disc_gage_info)

        # Get correct set of data series
        _logger.info('Getting correct set of data series for chart...')
        release_trans = _get_release_trans(disc_gage_info)

        # Export json file
        _logger.info('Writing JSON file...')
        _export_json(disc_gage_info, release_trans)

        # Import predicted json file
        _logger.info('Importing predicted JSON file...')
        _import_predicted_json(disc_gage_info)

        # Export predicted json file
        _logger.info('Exporting predicted JSON file...')
        _export_predicted_json(disc_gage_info, release_trans)

        # Export predicted data to dss (also convert water level to discharge)
        # for use with HEC-RAS
        _logger.info('Exporting predicted data for HEC-RAS...')
        _export_predicted_dss(disc_gage_info, release_trans)

        # Write chart
        _logger.info('Writing chart...')
        highcharts.write_chart(_current_time,
                               _hist_start,
                               _end_time,
                               release_trans,
                               disc_gage_info,
                               _MAIN_CONFIG,
                               _HECHMS_CONFIG)

    _logger.info('Done!')

    hechms_end = datetime.now()
    _logger.info('hechms_end: %s', hechms_end)
    _logger.info('hechms_duration: %s', hechms_end - hechms_start)


def _initialize(current_time, main_config, hechms_config):
    # Set current time globally
    _logger.info('Setting some parameters globally...')
    global _current_time
    _current_time = current_time
    global _MAIN_CONFIG
    _MAIN_CONFIG = main_config
    global _HECHMS_CONFIG
    _HECHMS_CONFIG = hechms_config

    # Get start and end time from current time and simulation range
    _logger.info('Getting start and end time from current time and simulation \
range...')
    global _start_time, _end_time
    _start_time = _current_time - _SIM_PAST_HOURS
    _end_time = _current_time + _SIM_FUTURE_HOURS
    _logger.info('_start_time: %s', _start_time)
    _logger.info('_end_time: %s', _end_time)

    # Get start time for historical data (rainfall and water level)
    _logger.info('Getting start time for historical data (rainfall and water \
level)...')
    global _hist_start
    _hist_start = _current_time - _HIST_DAYS
    _logger.info('_hist_start: %s', _hist_start)
    _logger.info('_RAIN_PAST_HOURS: %s', _RAIN_PAST_HOURS)


def _get_rainfall_data_in_mm():

    # Get rainfall data
    for prec_gage, prec_gage_info in \
            sorted(_HECHMS_CONFIG.prec_gages.viewitems()):

        _logger.info('Precip gage: %s Location: %s', prec_gage,
                     prec_gage_info['sensor'].meta()['location'])

        # Fetch data
        prec_gage_info['sensor'].fetch_data(start_time=_hist_start,
                                            end_time=_current_time)

        _logger.debug("prec_gage_info['sensor'].data(): %s",
                      pprint.pformat(prec_gage_info['sensor'].data(), width=40))

        # Write dss
        prec_gage_info['sensor'].dss()

        _logger.debug("prec_gage_info['sensor'].dss().filepath(): %s",
                      prec_gage_info['sensor'].dss().filepath())

    # _logger.debug('_HECHMS_CONFIG.prec_gages: %s',
    #               pprint.pformat(_HECHMS_CONFIG.prec_gages))


def _get_rainfall_data_in_mm_per_hr():

    # Accumulate rainfall for each hour
    for prec_gage, prec_gage_info in \
            sorted(_HECHMS_CONFIG.prec_gages.viewitems()):

        prec_gage_info['cumulative'] = {
            1: {}
        }

        hour_block = []
        # Group rainfall data in mm into hour blocks
        # Hour blocks start on the first minute of the hour, and ends on the
        # 60th minute the hour, e.g., 10:01-11:00 is an hour block
        for time, rainfall in sorted(prec_gage_info['sensor'].data().viewitems()):
            if hour_block:
                stime, _ = hour_block[0]
                if not ((stime.hour == time.hour and stime.minute != 0) or
                        (time.hour - stime.hour == 1 and time.minute == 0)):
                    # If a new block has started, sum the values of the
                    # previous block and add to rainfall data in mm/hr
                    ltime, _ = hour_block[-1]
                    prec_gage_info['cumulative'][
                        1][ltime] = sum(v for _, v in hour_block)
                    # Reset hour block
                    hour_block = []
            hour_block.append((time, rainfall))
        if hour_block:
            ltime, _ = hour_block[-1]
            prec_gage_info['cumulative'][1][
                ltime] = sum(v for _, v in hour_block)

    # _logger.debug('_HECHMS_CONFIG.prec_gages: %s',
    #               pprint.pformat(_HECHMS_CONFIG.prec_gages))


def _get_cumulative_rainfall():

    cumulative_rainfall = {}
    cumhr_min = 3
    cumhr_max = 24

    for prec_gage, prec_gage_info in \
            sorted(_HECHMS_CONFIG.prec_gages.viewitems()):

        # Initialize cumulative rainfall
        cumhr = cumhr_min
        while cumhr <= cumhr_max:
            cumulative_rainfall[cumhr] = 0
            if not cumhr in prec_gage_info['cumulative']:
                prec_gage_info['cumulative'][cumhr] = {}
            cumhr *= 2

        # Accumulate rainfall
        for dt, rainfall in sorted(prec_gage_info['cumulative'][1].viewitems()):

            cumhr = cumhr_min
            while cumhr <= cumhr_max:
                # Add current rainfall to cumulative rainfall
                cumulative_rainfall[cumhr] += rainfall

                # Add current cumulative rainfall to all dict
                prec_gage_info['cumulative'][cumhr][dt] = \
                    cumulative_rainfall[cumhr]

                # Reset cumulative rainfall if current hour is divisible by
                # accumlate hour
                if dt.hour % cumhr == 0:
                    cumulative_rainfall[cumhr] = 0

                cumhr *= 2

    _logger.debug('_HECHMS_CONFIG.prec_gages: %s',
                  pprint.pformat(_HECHMS_CONFIG.prec_gages))


def _get_waterlevel_data():

    # Get water level data
    for disc_gage, disc_gage_info in \
            sorted(_HECHMS_CONFIG.disc_gages.viewitems()):

        _logger.info('Discharge gage: %s Location: %s', disc_gage,
                     disc_gage_info['sensor'].meta()['location'])

        # Get water level data and store it in a dss file
        # Water level data time range will be from historical start until
        # end time
        st = _hist_start
        if not _MAIN_CONFIG.testing:
            _logger.info('Release version: Only getting water level data up \
to current time: %s', _current_time)
            et = _current_time
        else:
            _logger.info('Testing version: Getting water level data up to \
end time: %s', _end_time)
            et = _end_time

        # Fetch data
        try:
            disc_gage_info['sensor'].fetch_data(start_time=st, end_time=et)

            _logger.debug("disc_gage_info['sensor'].data(): %s",
                          pprint.pformat(disc_gage_info['sensor'].data()))

            # If there are no water level MSL data, fetch non-MSL
            if not disc_gage_info['sensor'].data():
                _logger.info('Fetching non-MSL water level data...')

                # Set data type to waterlevel only
                disc_gage_info['sensor'].data_type('waterlevel')

                # Fetch data again
                disc_gage_info['sensor'].fetch_data(start_time=st, end_time=et)

                _logger.debug("disc_gage_info['sensor'].data(): %s",
                              pprint.pformat(disc_gage_info['sensor'].data()))

            # Write dss
            # disc_gage_info['sensor'].dss()

            # _logger.debug("disc_gage_info['sensor'].dss().filepath(): %s",
            #               disc_gage_info['sensor'].dss().filepath())

            # Add water level offset
            o = disc_gage_info['waterlevel_offset']
            for t in disc_gage_info['sensor'].data().viewkeys():
                disc_gage_info['sensor'].data()[t] += o

        except Exception:
            _logger.info('Error fetching actual water level data. \
Continuing...')

    _logger.debug('_HECHMS_CONFIG.disc_gages: %s',
                  pprint.pformat(_HECHMS_CONFIG.disc_gages, width=40))


def _run_hechms():

    # Setup HEC-HMS first
    _logger.info('Initializing HEC-HMS...')
    interval = _initialize_hechms()

    #
    # Run HEC-HMS
    #
    _logger.info('Running HEC-HMS...')

    # Change directory to HMS directory
    cur_dir = os.getcwd()
    os.chdir(_MAIN_CONFIG.hechms_dir)

    # Run HEC-HMS
    hms = subprocess.call([_MAIN_CONFIG.hechms_cmd, '-s',
                           _HECHMS_CONFIG.comp_script])
    if hms != 0:
        _logger.error('Error while running HEC-HMS.cmd! Exiting.')
        exit(1)

    # Change back to current directory
    os.chdir(cur_dir)
    _logger.info('Success running HEC-HMS.')


def _initialize_hechms():

    #
    # Update control specs file
    #
    # global _start_time
    _logger.info('Updating control specs file...')
    _logger.debug('_start_time: %s', _start_time)
    _logger.debug('_end_time: %s', _end_time)
    _logger.debug('_MAIN_CONFIG.interval: %s', _MAIN_CONFIG.interval)

    # Read current control specs
    buf = []
    for _, line in main_control.text_file_line_gen(_HECHMS_CONFIG.ctrl_specs):
        if 'Start Date' in line:
            buf.append('Start Date: ' + _start_time.strftime('%d %B %Y'))
        elif 'Start Time' in line:
            buf.append('Start Time: ' + _start_time.strftime('%H:%M'))
        elif 'End Date' in line:
            buf.append('End Date: ' + _end_time.strftime('%d %B %Y'))
        elif 'End Time' in line:
            buf.append('End Time: ' + _end_time.strftime('%H:%M'))
        elif 'Time Interval' in line:
            buf.append('Time Interval: ' + str(_MAIN_CONFIG.interval))
        else:
            buf.append(line)

    # Write new control specs file
    with open(_HECHMS_CONFIG.ctrl_specs, 'w') as open_file:
        open_file.write('\n'.join(buf))

    #
    # Update prec gages info in the time series data file #
    #
    _logger.info('Updating time series data file...')

    # Read current prec gages info from time series data file
    buf = []
    prec_gage = None
    for _, line in main_control.text_file_line_gen(_HECHMS_CONFIG.ts_data):
        if prec_gage:
            sensor = _HECHMS_CONFIG.prec_gages[prec_gage]['sensor']
            dss = sensor.dss()
            if 'Data Type' in line:
                buf.append('Data Type: ' + dss.dsstype())
            elif 'Local to Project' in line:
                buf.append('Local to Project: NO')
            elif 'Start Time' in line:
                buf.append('Start Time: ' +
                           sensor.start_time().strftime('%d %B %Y, %H:%M'))
            elif 'End Time' in line:
                buf.append('End Time: ' +
                           sensor.end_time().strftime('%d %B %Y, %H:%M'))
            elif 'DSS File' in line:
                buf.append('DSS File: ' + dss.filepath())
            elif 'Pathname' in line:
                buf.append('Pathname: ' + dss.fullname())
            elif 'End' in line:
                buf.append(line)
                prec_gage = None
            else:
                buf.append(line)
        else:
            for gage in _HECHMS_CONFIG.prec_gages.keys():
                if 'Gage: ' + gage == line:
                    prec_gage = gage
                    break
            buf.append(line)

    # Write new time series data info
    with open(_HECHMS_CONFIG.ts_data, 'w') as open_file:
        open_file.write('\n'.join(buf))

    #
    # Check if compute script is valid
    #
    _logger.info('Checking if compute script is valid...')

    # Read current compute script
    buf = []
    new_comp_script = False
    for _, line in main_control.text_file_line_gen(_HECHMS_CONFIG.comp_script):
        if 'OpenProject' in line:
            tokens = re.split(r'[()," ]+', line)[:-1]
            if (_HECHMS_CONFIG.hechms_proj_name != tokens[1] or
                    _HECHMS_CONFIG.hechms_proj_dir != tokens[2]):
                buf.append('OpenProject("' + _HECHMS_CONFIG.hechms_proj_name +
                           '", "' + _HECHMS_CONFIG.hechms_proj_dir + '")')
                new_comp_script = True
            else:
                buf.append(line)
        elif 'Compute' in line:
            tokens = re.split(r'[(),"]+', line)[:-1]
            if _HECHMS_CONFIG.hechms_proj_name != tokens[1]:
                buf.append('Compute("' + _HECHMS_CONFIG.hechms_proj_name +
                           '")')
            else:
                buf.append(line)
        else:
            buf.append(line)

    # Write new compute script if necessary
    if new_comp_script:
        _logger.info('Writing new compute script...')
        with open(_HECHMS_CONFIG.comp_script, 'w') as open_file:
            open_file.write('\n'.join(buf))
    else:
        _logger.info('Current compute script valid.')


def _read_hechms_output(disc_gage, disc_gage_info):

    # Get discharge dss path/s
    _logger.info('Getting discharge dss path/s...')
    disc_dss_paths = []
    t = _start_time
    while t < _end_time + timedelta(days=1):
        path_parts = ['',
                      disc_gage,
                      'FLOW',
                      t.strftime('%d%b%Y').upper(),
                      str(_MAIN_CONFIG.interval) + 'MIN',
                      'RUN:' + str(_HECHMS_CONFIG.hechms_proj_name).upper()]
        disc_dss_paths.append('/' + '/'.join(path_parts) + '/')
        t += timedelta(days=1)
    _logger.debug('disc_dss_paths: %s', pprint.pformat(disc_dss_paths))

    # Get discharge from dss file
    _logger.info('Getting discharge from dss...')

    d = DSSFile(_HECHMS_CONFIG.disc_dss_file_path)
    d.start_time(_start_time)
    d.end_time(_end_time)
    d.read(disc_dss_paths)

    disc_gage_info['predicted'] = {}
    disc_gage_info['predicted']['discharge'] = {
        'hechms_output': d.data()
    }


def _convert_discharge_to_waterlevel(disc_gage_info):

    # Convert discharge to water level and data to _waterlevel_data
    disc_gage_info['predicted']['waterlevel'] = {_PSERIES: {}}
    for t, d in \
            sorted(disc_gage_info['predicted']['discharge']
                   ['hechms_output'].viewitems()):
        try:
            w = discharge2waterlevel(disc_gage_info, d)
        except ValueError:
            _logger.exception('Error converting discharge to waterlevel!')
            _logger.error('discharge: %s', d)
            exit(1)
        disc_gage_info['predicted']['waterlevel'][_PSERIES][t] = w

    _logger.debug('_HECHMS_CONFIG.disc_gages: %s',
                  pprint.pformat(_HECHMS_CONFIG.disc_gages))


def _run_linear_regress_with_outlier_removal(disc_gage_info):

    # Collect data for linear regression
    xs = []
    ys = []
    for t, a in sorted(disc_gage_info['sensor'].data().viewitems()):
        if t in disc_gage_info['predicted']['waterlevel'][_PSERIES]:
            xs.append(
                disc_gage_info['predicted']['waterlevel'][_PSERIES][t])
            ys.append(a)

    _logger.debug('len(xs): %s', len(xs))
    _logger.debug('len(ys): %s', len(ys))

    # Skip if there's not enough data
    if len(xs) < 2 or len(ys) < 2:
        return

    _logger.debug('xs: %s', xs)
    _logger.debug('ys: %s', ys)

    # Compute linear regression
    slope, intercept, _, _, _ = scipy.stats.linregress(np.array(xs),
                                                       np.array(ys))
    _logger.debug('slope: %s, intercept: %s', slope, intercept)

    # Remove outliers until slope becomes positive
    while slope < 0:

        # Compute square errors
        errors = []
        for x, y in zip(xs, ys):
            error = (slope * x + intercept) ** 2
            errors.append((error, x, y))

        # Sort errors
        errors.sort()

        _logger.debug('Top 5 errors: %s', errors[-5:])

        # Remove top 5 largest errors
        errors = errors[:-5]

        # Repopulate xs and ys
        xs = []
        ys = []
        for _, x, y in errors:
            xs.append(x)
            ys.append(y)
        _logger.debug('xs: %s', xs)
        _logger.debug('ys: %s', ys)

        # Compute new slope and intercept
        slope, intercept, _, _, _ = scipy.stats.linregress(np.array(xs),
                                                           np.array(ys))
        _logger.debug('slope: %s, intercept: %s', slope, intercept)

    _logger.info('slope: %s, intercept: %s', slope, intercept)

    # Apply final slope and intercept to predicted water level
    disc_gage_info['predicted']['waterlevel'][_PLSERIES] = {}
    for t, p in \
            sorted(
            disc_gage_info['predicted']['waterlevel'][_PSERIES].viewitems()
            ):
        pl = slope * p + intercept
        disc_gage_info['predicted']['waterlevel'][_PLSERIES][t] = pl

    # Prepare offset
    disc_gage_info['offsets'][(_PLSERIES, _PLOSERIES)] = 0.


def _apply_tidal_correction(disc_gage_info):

    _logger.info('Getting tidal prediction...')

    # Export actual water level data
    _logger.info('Exporting actual water level data...')
    wl_actual = 'water_level_actual.csv'
    with open(wl_actual, 'w') as open_file:
        for t, a in \
                sorted(disc_gage_info['sensor'].data().viewitems()):
            if t <= _current_time:
                open_file.write(str(t) + ' ' + str(a) + '\n')

    #
    # TAPPY
    # (http://sourceforge.net/apps/mediawiki/tappy/index.php?title=Main_Page)
    #
    # Run TAPPY analysis
    _logger.info('Running TAPPY analysis...')
    wl_def = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'water_level.def')
    wl_xml = 'water_level.xml'
    _logger.debug('wl_def: %s', wl_def)
    tappya = subprocess.call(['tappy.py', 'analysis', wl_actual,
                              '--def_filename', wl_def, '--outputxml', wl_xml],
                             shell=True)
    if tappya != 0:
        _logger.error('Error while running tappy analysis! Exiting.')
        exit(1)

    # Run TAPPY prediction
    # Prediction length needs to be more than 13 hours as required by TAPPY
    _logger.info('Running TAPPY prediction...')
    tappy_time_fmt = '%Y-%m-%dT%H:%M:%S'
    start_date = _hist_start.strftime(tappy_time_fmt)
    end_date = _end_time.strftime(tappy_time_fmt)
    _logger.debug('start_date: %s', start_date)
    _logger.debug('end_date: %s', end_date)
    wl_predict = 'water_level_predict.csv'
    tappyp = subprocess.call(['tappy.py', 'prediction', wl_xml, start_date,
                              end_date, str(_MAIN_CONFIG.interval), '--fname',
                              wl_predict], shell=True)
    if tappyp != 0:
        _logger.error('Error while running tappy prediction! Exiting.')
        exit(1)

    # Read tidal prediction
    _logger.info('Reading and applying tidal prediction/correction...')
    disc_gage_info['predicted']['waterlevel'][_TSERIES] = {}
    tide_sum = 0
    counter = 0
    for _, line in main_control.text_file_line_gen(wl_predict):
        tokens = line.split()
        # Get time
        t = datetime.strptime(tokens[0], '%Y-%m-%dT%H:%M:%S')
        # Get tide
        tide = float(tokens[1])
        # Set tide data
        disc_gage_info['predicted']['waterlevel'][_TSERIES][t] = tide
        # Get tide sum
        tide_sum += tide
        counter += 1

    # Delete temporary files
    _logger.info('Deleting temporary files...')
    os.remove(wl_actual)
    os.remove(wl_xml)
    os.remove(wl_predict)

    # Get tide average
    tide_avg = tide_sum / float(counter)

    # Get predicted + tidal prediction - tide_average
    _logger.info('Getting predicted + tidal prediction - tide average \
series...')
    disc_gage_info['predicted']['waterlevel'][_PTSERIES] = {}
    for t, p in \
            sorted(disc_gage_info['predicted']['waterlevel']
                   [_PSERIES].viewitems()):
        if t in disc_gage_info['predicted']['waterlevel'][_TSERIES]:
            tide = disc_gage_info['predicted']['waterlevel'][_TSERIES][t]
            pt = p + tide - tide_avg
            disc_gage_info['predicted']['waterlevel'][_PTSERIES][t] = pt


def _get_predicted_offset(disc_gage_info):

    # Get offset
    for t, a in sorted(disc_gage_info['sensor'].data().viewitems(),
                       reverse=True):
        if t <= _current_time:
            for k in disc_gage_info['offsets'].viewkeys():
                s, _ = k
                if s in disc_gage_info['predicted']['waterlevel']:
                    try:
                        offset = a - \
                            disc_gage_info['predicted']['waterlevel'][s][t]
                        disc_gage_info['offsets'][k] = offset
                    except Exception:
                        _logger.exception(
                            'Error getting water level @t: %s s: %s', t, s)
                        exit(1)
            break

    _logger.debug("disc_gage_info['offsets']: %s",
                  pprint.pformat(disc_gage_info['offsets']))

    # Apply offset
    for k, o in disc_gage_info['offsets'].viewitems():
        s, d = k
        for t, p in \
                sorted(disc_gage_info['predicted']['waterlevel']
                       [s].viewitems()):
            if d not in disc_gage_info['predicted']['waterlevel']:
                disc_gage_info['predicted']['waterlevel'][d] = {}
            disc_gage_info['predicted']['waterlevel'][d][t] = p + o

    # _logger.debug('_HECHMS_CONFIG.disc_gages: %s',
    #               pprint.pformat(_HECHMS_CONFIG.disc_gages))


def _get_release_trans(disc_gage_info):

    release_trans = {_OPSERIES: _OPSERIES}

    has_series = False
    for series_prio in disc_gage_info['pseries_prio']:

        _logger.debug('series_prio: %s', series_prio)
        sp = eval(series_prio)
        _logger.debug('sp: %s', sp)

        for series_key in _PSERIES_KEYS:

            _logger.debug('series_key: %s', series_key)

            if (sp == series_key and
                    series_key in disc_gage_info['predicted']['waterlevel']):
                release_trans['Predicted'] = series_key
                has_series = True
                break

        if has_series:
            break

    if not has_series:
        # _logger.error('Matching priority predicted series not found!')
        # _logger.error('Exiting.')
        # exit(1)
        release_trans['Predicted'] = _PSERIES

    _logger.debug('release_trans: %s', release_trans)

    return release_trans


def _sanitize(t):
    return t.replace(' ', '_').replace(',', '').lower()


def _export_json(disc_gage_info, release_trans):

    json_fn = op.join(_MAIN_CONFIG.json_dir,
                      _sanitize(disc_gage_info['sensor'].meta()['location']) +
                      '.json')

    data = {}
    for t, w in sorted(disc_gage_info['predicted']['waterlevel']
                       [release_trans['Predicted']].viewitems()):
        data[str(t)] = w

    json.dump(data, open(json_fn, 'w'), sort_keys=True, indent=4)


def _import_predicted_json(disc_gage_info):

    json_fn = op.join(_MAIN_CONFIG.json_dir,
                      _sanitize(disc_gage_info['sensor'].meta()['location']) +
                      '_predicted.json')

    # disc_wl_data[_OPSERIES] = {}
    disc_gage_info['predicted']['waterlevel'][_OPSERIES] = {}
    if os.path.isfile(json_fn):
        data = json.load(open(json_fn, 'r'))
        for dt_str, wl in data.items():
            dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
            disc_gage_info['predicted']['waterlevel'][_OPSERIES][dt] = wl


def _export_predicted_json(disc_gage_info, release_trans):

    wl = disc_gage_info['predicted']['waterlevel'][release_trans['Predicted']][
        _current_time + timedelta(hours=1)]
    disc_gage_info['predicted']['waterlevel'][_OPSERIES][
        _current_time + timedelta(hours=1)] = wl

    data = {}
    for dt, wl in disc_gage_info['predicted']['waterlevel'][_OPSERIES].items():
        if dt >= _current_time - _HIST_DAYS:
            data[str(dt)] = wl

    json_fn = op.join(_MAIN_CONFIG.json_dir,
                      _sanitize(disc_gage_info['sensor'].meta()['location']) +
                      '_predicted.json')

    json.dump(data, open(json_fn, 'w'), sort_keys=True, indent=4)


def _export_predicted_dss(disc_gage_info, release_trans):

    # Convert water level to discharge
    _logger.info('Converting water level to discharge...')
    disc_gage_info['predicted']['discharge']['hecras_input'] = {}
    for t, w in \
            sorted(disc_gage_info['predicted']['waterlevel']
                   [release_trans['Predicted']].viewitems()):
        d = waterlevel2discharge(disc_gage_info, w)
        disc_gage_info['predicted']['discharge']['hecras_input'][t] = d

    # Contruct full name
    fullname = [
        _sanitize(disc_gage_info['sensor'].meta()['province']).upper(),
        _sanitize(disc_gage_info['sensor'].meta()['location']).upper(),
        'FLOW',
        _current_time.strftime('%d%b%Y').upper(),
        str(_MAIN_CONFIG.interval) + 'MIN',
        'FORECAST'
    ]

    # Write dss
    d = DSSFile()
    d.data(disc_gage_info['predicted']['discharge']['hecras_input'])
    d.dsstype('INST-VAL')
    d.fullname(fullname)
    d.units('m3/s')
    d.write()
    d.start_time(_current_time)
    d.end_time(_end_time)
    disc_gage_info['predicted']['discharge']['dss'] = d

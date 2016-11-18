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
from main_control import discharge2waterlevel, waterlevel2discharge
import copy
import fractions
import highcharts
import logging
import math
import numpy as np
import os
import os.path as op
import pickle
import re
import repo_handler
import scipy.stats
import subprocess
import collections
import json
import main_control
import pprint

_version = '2.19.1'
print(os.path.basename(__file__) + ': v' + _version)
np.seterr(all='raise')
_logger = logging.getLogger()
_SIM_PAST_HOURS = timedelta(hours=36)
_SIM_FUTURE_HOURS = timedelta(hours=12)
_RAIN_PAST_HOURS = timedelta(hours=12)
_HIST_DAYS = timedelta(days=7)
_BF_HT_DIFF = 0.020  # meters
_BF_KERN_SIZE = 7  # samples
_ASERIES = 'Actual'
_TSERIES = 'Tidal Prediction'
_PLSERIES = 'HEC-HMS w/ LinRegress(x-P,y-A)'
_PLOSERIES = _PLSERIES + ' + offset'
_OPSERIES = 'Old Predicted'


def hechms_control(current_time, main_config, hechms_config):
    hechms_start = datetime.now()
    _logger.info('hechms_start = %s', hechms_start)
    _logger.info('Initializing...')
    _initialize(current_time, main_config, hechms_config)
    # Get rainfall data in mm
    _logger.info('Getting rainfall data (in mm)...')
    global _rainfall_data_in_mm
    _rainfall_data_in_mm, is_rain_now, has_rain_past = \
        _get_rainfall_data_in_mm()
    # Reflect rain (flip and copy rain from 6 hours before onto 6 hours after,
    # where 6 hours is the number of hours to simulate in the future)
    # _reflect_rain()
    # Get rainfall data in mm/hr
    _logger.info('Getting rainfall data (in mm/hr)...')
    global _rainfall_data_in_mm_per_hour
    _rainfall_data_in_mm_per_hour = _get_rainfall_data_in_mm_per_hr()
    # _rainfall_data_cumulative = {'mm/hr (1hr cum)': rainfall_data_in_mm_per_hr,
    #                            'mm/hr (3hr cum)': None,
    #                            'mm/hr (6hr cum)': None,
    #                            'mm/hr (12hr cum)': None,
    #                            'mm/hr (24hr cum)': None}
    # Get cumulative rainfall
    _logger.info('Getting cumulative rainfall...')
    _rainfall_data_cumulative = _get_cumulative_rainfall2()
    _logger.debug('_rainfall_data_cumulative = %s', pprint.pformat(
        _rainfall_data_cumulative, indent=4, width=160))
    # Get water level data
    _logger.info('Getting water level data...')
    global _waterlevel_data
    _waterlevel_data = _get_waterlevel_data()
    # Start simulation
    _logger.info('Starting simulation...')
    _logger.info('is_rain_now = %s', is_rain_now)
    _logger.info('has_rain_past = %s', has_rain_past)
    subtitle = ''
    global _PSERIES
    if not is_rain_now and not has_rain_past:
        subtitle = ('not raining now, has not rained in the past ' +
                    str(_RAIN_PAST_HOURS.seconds / (60 * 60)) + ' hours, ' +
                    '_no_rain()')
        _logger.debug('subtitle = %s', subtitle)
        #
        _PSERIES = 'LinRegress(x-T,y-A)'
        _no_rain()
        has_ran_hec_hms = False
        #
    else:
        if not is_rain_now and has_rain_past:
            subtitle += ('not raining now, has rained in the past ' +
                         str(_RAIN_PAST_HOURS.seconds / (60 * 60)) +
                         ' hours')
            if _HECHMS_CONFIG.rainfall_scenarios:
                _logger.info('Using rainfall scenarios...')
                subtitle += ', _rainfall_scenarios()'
                #
                _rainfall_scenarios()
                #
            else:
                subtitle += ', missing rainfall scenarios'
        elif is_rain_now and not has_rain_past:
            subtitle += ('raining now, has not rained in the past ' +
                         str(_RAIN_PAST_HOURS.seconds / (60 * 60)) + ' hours')
        elif is_rain_now and has_rain_past:
            subtitle += ('raining now, has rained in the past ' +
                         str(_RAIN_PAST_HOURS.seconds / (60 * 60)) + ' hours')
        subtitle += ', run_hms()'
        _logger.debug('subtitle = %s', subtitle)
        #
        _PSERIES = 'HEC-HMS'
        _run_hechms()
        has_ran_hec_hms = True
        #
    # Write chart for each discharge gage
    _logger.info('Writing charts for each discharge gage...')
    global _POSERIES, _PTSERIES, _PTOSERIES
    _POSERIES = _PSERIES + ' + offset'
    _PTSERIES = _PSERIES + ' + ' + _TSERIES
    _PTOSERIES = _PTSERIES + ' + offset'
#    exported_dss = {}
    exported_dss = collections.OrderedDict()
    for disc_gage, disc_gage_info in _HECHMS_CONFIG.disc_gages.items():
        # Get interval of discharge gage
        interval = disc_gage_info['dss_info'].interval
        _logger.debug('interval = %s', interval)
        # Get base series
        base_series = disc_gage_info['base_series']
        _logger.debug('base_series = %s', base_series)
        # Get predicted offset to actual
        _logger.info('Getting the offset of predicted to actual...')
        _get_predicted_offset(_PSERIES, _POSERIES, disc_gage, interval)
        # Check if tidal correction is needed
        if disc_gage_info['tidal_correct']:
            _logger.info('Applying tidal correction...')
            _apply_tidal_correction(disc_gage, interval)
        # Get correct set of data series
        _logger.info('Getting correct set of data series for chart...')
        release_trans = _get_release_trans(has_ran_hec_hms,
                                           disc_gage, disc_gage_info)
        _logger.debug('release_trans = %s', release_trans)
        _logger.debug('_waterlevel_data[disc_gage].keys() = %s',
                      _waterlevel_data[disc_gage].keys())
        # Export json file
        _logger.info('Writing JSON file...')
        _export_json(base_series, release_trans, _waterlevel_data[disc_gage])
        # Import predicted json file
        _logger.info('Importing predicted JSON file...')
        _import_predicted_json(base_series, _waterlevel_data[disc_gage])
        # Export predicted json file
        _logger.info('Exporting predicted JSON file...')
        _export_predicted_json(base_series, release_trans,
                               _waterlevel_data[disc_gage])
        # Write chart
        _logger.info('Writing chart...')
        highcharts.write_chart(_waterlevel_data[disc_gage],
                               _rainfall_data_cumulative,
                               base_series,
                               subtitle,
                               _current_time,
                               _hist_start,
                               _end_time,
                               _MAIN_CONFIG.charts_dir,
                               _MAIN_CONFIG.testing,
                               release_trans,
                               disc_gage_info['min_waterlevel'],
                               disc_gage_info['max_waterlevel'])
        # Get average differences if testing and HEC-HMS has been run
        # if _MAIN_CONFIG.testing and has_ran_hec_hms:
        #     _logger.info('Getting average differences...')
        #     _get_avg_diffs(disc_gage, base_series)
        # Export predicted data to dss (also convert water level to discharge)
        # for use with HEC-RAS
        _logger.info('Exporting predicted data for HEC-RAS...')
        # Get primary discharge gage
        dss_file, dss_info = _export_predicted_data(disc_gage, disc_gage_info,
                                                    release_trans)
        exported_dss[base_series] = {'dss_file': dss_file,
                                     'dss_info': dss_info}
    _logger.debug('exported_dss = %s', exported_dss)
    _logger.info('Done!')
    hechms_end = datetime.now()
    _logger.info('hechms_end = %s', hechms_end)
    _logger.info('hechms_duration = %s', hechms_end - hechms_start)
    return exported_dss


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
    _logger.info('_start_time = %s', _start_time)
    _logger.info('_end_time = %s', _end_time)
    # Get start time for historical data (rainfall and water level)
    _logger.info('Getting start time for historical data (rainfall and water \
level)...')
    global _hist_start
    _hist_start = _current_time - _HIST_DAYS
    _logger.info('_hist_start = %s', _hist_start)
    _logger.info('_RAIN_PAST_HOURS = %s', _RAIN_PAST_HOURS)


def _get_rainfall_data_in_mm():
    # Get rainfall data
    # Also check it is currently raining and/or
    # if it rained in the past X hours
    rainfall_data_in_mm = {}
    is_rain_now = False
    has_rain_past = False
    for _, prec_gage_info in _HECHMS_CONFIG.prec_gages.items():
        _logger.info('Precip gage: %s', prec_gage_info['base_series'])
        # Get repo ID
        prec_repoID = prec_gage_info['repoID']
        _logger.debug('prec_repoID = %s', prec_repoID)
        # Get rainfall data and store it in a dss file
        # Rainfall data time range will only be from historical start until
        # current time
        (dss_file, dss_info,
         raw_data) = repo_handler.get_dss(prec_repoID, _hist_start,
                                          _MAIN_CONFIG.cache_dir,
                                          not _MAIN_CONFIG.testing,
                                          _MAIN_CONFIG,
                                          end_time=_current_time,
                                          proxy=_MAIN_CONFIG.proxy)
        if len(dss_file) > 1:
            _logger.error('Illegal program state!')
            _logger.error('Length of dss_file should still be 1. Exiting.')
            exit(1)
        # Add dss file and info to dict
        prec_gage_info['dss_file'] = dss_file[0]
        prec_gage_info['dss_info'] = dss_info
        _logger.debug('dss_file[0] = %s', dss_file[0])
        _logger.debug('dss_info = %s', dss_info)
        # Get sensor name
        if len(raw_data['data']) > 1:
            _logger.error('Illegal program state!')
            _logger.error("Length of raw_data['data'] should still be 1.")
            _logger.error('Exiting.')
            exit(1)
        sensor_name = raw_data['data'].keys()[0]
        _logger.debug('sensor_name = %s', sensor_name)
        _logger.debug('raw_data = %s', raw_data)
        # Get interval
        interval = float(dss_info.interval)
        _logger.debug('interval = %s', interval)
        # Add rainfall prec_gage_info to rainfall data
        series_name = repo_handler.id_format(prec_repoID.identifier)
        prec_gage_info['series_name'] = series_name
        _logger.debug('series_name = %s', series_name)
        rainfall_data_in_mm[series_name] = {}
        for time, rainfall_in_mm in raw_data['data'][sensor_name].items():
            rainfall_data_in_mm[series_name][time] = rainfall_in_mm
        # Check if it is currently raining
        _logger.info('Checking if it is currently raining...')
        if not is_rain_now:
            is_rain_now, _ = _is_raining(rainfall_data_in_mm[series_name],
                                         timedelta(minutes=interval))
        # Check if it has rained in the past X hours
        _logger.info('Checking if it has rained in the past X hours...')
        if not has_rain_past:
            has_rain_past, _ = _is_raining(rainfall_data_in_mm[series_name],
                                           _RAIN_PAST_HOURS,
                                           lambda a, b, c: (timedelta(minutes=0) <
                                                            a - b <= c))
    _logger.info('is_rain_now = %s', is_rain_now)
    _logger.info('has_rain_past = %s', has_rain_past)
    _logger.debug('_HECHMS_CONFIG.prec_gages = %s', _HECHMS_CONFIG.prec_gages)
    _logger.debug('rainfall_data_in_mm = %s', rainfall_data_in_mm)
    return rainfall_data_in_mm, is_rain_now, has_rain_past


def _is_raining(data, delta, comp=lambda a, b, c: a - b < c):
    for time, value in sorted(data.items(), reverse=True):
        if comp(_current_time, time, delta) and value > 0:
            _logger.info('It is/was raining!')
            _logger.info('%s: %s', time, value)
            return True, value
    return False, 0.


def _reflect_rain():
    if _HECHMS_CONFIG.reflect_mins > 0:
        _logger.info('Reflecting rain...')
        # Copy current rainfall data to new rainfall data
        new_rainfall_data = {}
        for k, v in _rainfall_data_in_mm.items():
            new_rainfall_data[k] = copy.deepcopy(v)
        # Get reflect start time
        reflect_start = (_current_time -
                         timedelta(minutes=_HECHMS_CONFIG.reflect_mins))
        _logger.debug('reflect_start = %s', reflect_start)
        _logger.debug('_current_time = %s', _current_time)
        for series_name, rainfall_data in _rainfall_data_in_mm.items():
            for time, rainfall in sorted(rainfall_data.items()):
                if reflect_start <= time < _current_time:
                    diff = _current_time - time
                    new_rainfall_data[series_name][_current_time + diff] = \
                        rainfall
        _logger.debug('new_rainfall_data = %s', new_rainfall_data)
        _update_rainfall_dss(new_rainfall_data)


def _reflect_rain2():

    def _get_latest_rainfall(rainfall_data):
        for time, rainfall in sorted(rainfall_data.items(), reverse=True):
            if rainfall > 0:
                return time, rainfall

    if _HECHMS_CONFIG.reflect_mins > 0:
        # Copy current rainfall data to new rainfall data
        new_rainfall_data = {}
        for k, v in _rainfall_data_in_mm.items():
            new_rainfall_data[k] = copy.deepcopy(v)

        reflect_mins = timedelta(minutes=_HECHMS_CONFIG.reflect_mins)
        interval = timedelta(minutes=_MAIN_CONFIG.interval)
        # For each rainfall series
        for series_name, rainfall_data in _rainfall_data_in_mm.items():
            _logger.debug('series_name = %s', series_name)
            # Get latest rain
            latest_time, latest_rainfall = _get_latest_rainfall(rainfall_data)
            _logger.debug('latest_time = %s', latest_time)
            _logger.debug('latest_rainfall = %s', latest_rainfall)
            # Get end time
            reflect_end = latest_time + reflect_mins
            _logger.debug('reflect_end = %s', reflect_end)
            # Generate theoretical decreasing rainfall
            current_time = _current_time + interval
            while current_time <= reflect_end:
                _logger.debug('current_time = %s', current_time)
                numerator = (current_time - latest_time).total_seconds() / 60.
                _logger.debug('numerator = %s', numerator)
                slope = numerator / float(_HECHMS_CONFIG.reflect_mins)
                _logger.debug('slope = %s', slope)
                generated_rainfall = latest_rainfall * (1 - slope)
                _logger.debug('generated_rainfall = %s', generated_rainfall)
                new_rainfall_data[series_name][
                    current_time] = generated_rainfall
                current_time += interval
                _logger.debug('#' * 40)
        _logger.debug('new_rainfall_data = %s', sorted(new_rainfall_data))
        _update_rainfall_dss(new_rainfall_data)


def _update_rainfall_dss(new_rainfall_data):
    # Update dss files
    _logger.info('Updating dss files...')
    for _, prec_gage_info in _HECHMS_CONFIG.prec_gages.items():
        dss_file = prec_gage_info['dss_file']
        dss_path = prec_gage_info['dss_info'].fullName
        dss_path_parts = dss_path.split('/')
        # Assuming Part E is IR-MONTH
        dss_path_parts[4] = _hist_start.strftime('01%b%Y').upper()
        _logger.debug('dss_path_parts = %s', dss_path_parts)
        dss_path = '/'.join(dss_path_parts)
        interval = prec_gage_info['dss_info'].interval
        data = new_rainfall_data[prec_gage_info['series_name']]
        # Create dss handler input
        dss_handler_in = {'dss_file': dss_file,
                          'dss_path': dss_path,
                          'interval': interval,
                          'data': data}
        output_file = repo_handler.dss_handler(dss_handler_in, ['update'],
                                               _MAIN_CONFIG)
        # Delete output file
        os.remove(output_file)


def _get_rainfall_data_in_mm_per_hr():
    # Accumulate rainfall for each hour
    rainfall_data_in_mm_per_hr = {}
    for location, data in _rainfall_data_in_mm.items():
        rainfall_data_in_mm_per_hr[location] = {}
        hour_block = []
        # Group rainfall data in mm into hour blocks
        # Hour blocks start on the first minute of the hour, and ends on the
        # 60th minute the hour, e.g., 10:01-11:00 is an hour block
        for time, rainfall in sorted(data.items()):
            if hour_block:
                stime, _ = hour_block[0]
                if not ((stime.hour == time.hour and stime.minute != 0) or
                        (time.hour - stime.hour == 1 and time.minute == 0)):
                    # If a new block has started, sum the values of the
                    # previous block and add to rainfall data in mm/hr
                    ltime, _ = hour_block[-1]
                    rainfall_data_in_mm_per_hr[location][ltime] = \
                        sum(v for _, v in hour_block)
                    # Reset hour block
                    hour_block = []
            hour_block.append((time, rainfall))
        if hour_block:
            ltime, _ = hour_block[-1]
            rainfall_data_in_mm_per_hr[location][ltime] = \
                sum(v for _, v in hour_block)
    _logger.debug('rainfall_data_in_mm_per_hr = %s',
                  rainfall_data_in_mm_per_hr)
    return rainfall_data_in_mm_per_hr


def _get_cumulative_rainfall():
    rainfall_data_cumulative = {1: _rainfall_data_in_mm_per_hour}
    # Cumulative hour blocks: 3, 6, 12, 24
    cumhr = 3
    while cumhr <= 24:
        _logger.debug('cumhr = %s', cumhr)
        # For each rainfall data
        rainfall_data_cumulative_temp = {}
        for location, data in _rainfall_data_in_mm_per_hour.items():
            rainfall_data_cumulative_temp[location] = {}
            # Cumulate rainfall data for the corresponding cumulative hour
            cumulative_block = []
            cumhr_mark_hr = -1
            for dt, rainfall in sorted(data.viewitems()):

                if cumulative_block:
                    # Initialize cumulative hour mark
                    if cumhr_mark_hr == -1:
                        # Get first entry from cumulative block
                        sdt, _ = cumulative_block[0]
                        # Get cumulative hour mark based on first data
                        # E.g. 2:00AM at 6HR cum -> 6:00AM cum. hour mark
                        cumhr_mark_hr = (sdt.hour / cumhr + 1) * cumhr
                        if cumhr_mark_hr == 24:
                            cumhr_mark_hr = 0
                        _logger.debug('cumhr_mark_hr = %s', cumhr_mark_hr)

                    # Get cum. hour mark for current datetime
                    cumhr_dt_hr = (dt.hour / cumhr + 1) * cumhr

                    # If the current cum. hour mark is different
                    if cumhr_mark_hr != cumhr_dt_hr:
                        # Get last datetime from block
                        ldt, _ = cumulative_block[-1]
                        # Get cum. report datetime
                        cumhr_dt = datetime(year=ldt.year, month=ldt.month,
                                            day=ldt.day, hour=cumhr_mark_hr,
                                            minute=0)
                        # Add cum. value to list
                        rainfall_data_cumulative_temp[location][cumhr_dt] = \
                            sum(v for _, v in cumulative_block)
                        # Reset cumulative block and cumhr_mark_hr
                        cumulative_block = []
                        cumhr_mark_hr = -1

                # Add current datetime, value to block
                cumulative_block.append((dt, rainfall))

        # Add cumulative rainfall data to all list
        _logger.info('Adding: ' + 'mm/hr (' + str(cumhr) + 'hr cum)')
        rainfall_data_cumulative[cumhr] = \
            copy.deepcopy(rainfall_data_cumulative_temp)

        # Get next cum. hour block
        cumhr *= 2

    return rainfall_data_cumulative


def _get_cumulative_rainfall2():
    rainfall_data_cumulative = {1: _rainfall_data_in_mm_per_hour}
    cumulative_rainfall = {}
    cumhr_min = 3
    cumhr_max = 24
    for location, data in _rainfall_data_in_mm_per_hour.items():

        # _logger.debug('location = %s', location)

        # Initialize cumulative rainfall
        cumhr = cumhr_min
        while cumhr <= cumhr_max:
            # _logger.debug('cumhr = %s', cumhr)
            cumulative_rainfall[cumhr] = 0
            rainfall_data_cumulative[cumhr][location] = {}
            cumhr *= 2

        # _logger.debug('cumulative_rainfall = %s', pformat(
        #     cumulative_rainfall, indent=4, width=160))
        # _logger.debug('rainfall_data_cumulative = %s', pformat(
        #     rainfall_data_cumulative, indent=4, width=160))

        # Accumulate rainfall
        for dt, rainfall in sorted(data.viewitems()):

            # _logger.debug('dt = %s rainfall = %s', dt, rainfall)

            cumhr = cumhr_min
            while cumhr <= cumhr_max:
                _logger.debug('cumhr = %s', cumhr)
                # Add current rainfall to cumulative rainfall
                cumulative_rainfall[cumhr] += rainfall
                # _logger.debug(
                #     'cumulative_rainfall[cumhr] = %s', cumulative_rainfall[cumhr])
                # Add current cumulative rainfall to all dict
                rainfall_data_cumulative[cumhr][location][dt] = \
                    cumulative_rainfall[cumhr]
                # _logger.debug('rainfall_data_cumulative[cumhr][location][dt] = %s', rainfall_data_cumulative[
                #               cumhr][location][dt])

                # Reset cumulative rainfall if current hour is divisible by
                # accumlate hour
                if dt.hour % cumhr == 0:
                    cumulative_rainfall[cumhr] = 0
                    # _logger.debug(
                    #     'cumulative_rainfall[cumhr] = %s', cumulative_rainfall[cumhr])

                cumhr *= 2

    return rainfall_data_cumulative


def _get_waterlevel_data():
    # Get water level data
    waterlevel_data = {}
    for disc_gage, disc_gage_info in _HECHMS_CONFIG.disc_gages.items():
        _logger.info('Discharge gage: %s', disc_gage_info['base_series'])
        waterlevel_data[disc_gage] = {}
        # Get repo ID
        disc_repoID = disc_gage_info['repoID']
        _logger.debug('disc_repoID = %s', disc_repoID)
        # Get water level data and store it in a dss file
        # Water level data time range will be from historical start until
        # end time
        if not _MAIN_CONFIG.testing:
            _logger.info('Release version: Only getting water level data up \
to current time: %s', _current_time)
            (dss_file, dss_info,
             raw_data) = repo_handler.get_dss(disc_repoID,
                                              _hist_start,
                                              _MAIN_CONFIG.cache_dir,
                                              not _MAIN_CONFIG.testing,
                                              _MAIN_CONFIG,
                                              end_time=_current_time,
                                              proxy=_MAIN_CONFIG.proxy)
        else:
            try:
                _logger.info('Testing version: Getting water level data up to \
    end time: %s', _end_time)
                (dss_file, dss_info,
                 raw_data) = repo_handler.get_dss(disc_repoID,
                                                  _hist_start,
                                                  _MAIN_CONFIG.cache_dir,
                                                  not _MAIN_CONFIG.testing,
                                                  _MAIN_CONFIG,
                                                  end_time=_end_time,
                                                  proxy=_MAIN_CONFIG.proxy)
            except Exception:
                _logger.info('Release version: Only getting water level data up \
to current time: %s', _current_time)
                (dss_file, dss_info,
                 raw_data) = repo_handler.get_dss(disc_repoID,
                                                  _hist_start,
                                                  _MAIN_CONFIG.cache_dir,
                                                  not _MAIN_CONFIG.testing,
                                                  _MAIN_CONFIG,
                                                  end_time=_current_time,
                                                  proxy=_MAIN_CONFIG.proxy)
        if len(dss_file) > 1:
            _logger.error('Illegal program state!')
            _logger.error('Length of dss_file should still be 1. Exiting.')
            exit(1)
        # Add dss file and info to dict
        disc_gage_info['dss_file'] = dss_file[0]
        disc_gage_info['dss_info'] = dss_info
        _logger.debug('dss_file[0] = %s', dss_file[0])
        _logger.debug('dss_info = %s', dss_info)
        # Get sensor name
        if len(raw_data['data']) > 1:
            _logger.error('Illegal program state!')
            _logger.error("Length of raw_data['data'] should still be 1.")
            _logger.error('Exiting.')
            exit(1)
        sensor_name = raw_data['data'].keys()[0]
        _logger.debug('sensor_name = %s', sensor_name)
        _logger.debug('raw_data = %s', raw_data)
        # Add raw data to water level data
        waterlevel_data[disc_gage][_ASERIES] = {}
        for time, value in raw_data['data'][sensor_name].items():
            waterlevel_data[disc_gage][_ASERIES][
                time] = value + disc_gage_info['WaterLevelOffset']
    _logger.debug('_HECHMS_CONFIG.disc_gages = %s', _HECHMS_CONFIG.disc_gages)
    _logger.debug('waterlevel_data = %s', waterlevel_data)
    return waterlevel_data


def _no_rain():
    _logger.info('No rain for the past %s hours.',
                 _RAIN_PAST_HOURS.seconds / (60 * 60))
    _logger.info('Doing a linear regression on past water levels \
to get future water levels...')
    # For each discharge gage
    for disc_gage, disc_gage_info in _HECHMS_CONFIG.disc_gages.items():
        _logger.debug('disc_gage = %s', disc_gage)
        interval = disc_gage_info['dss_info'].interval
        xs = []
        ys = []
        for time, waterlevel in \
                _waterlevel_data[disc_gage][_ASERIES].items():
            xs.append((_hist_start - time).total_seconds())
            ys.append(waterlevel)
        x = np.array(xs)
        y = np.array(ys)
        slope, intercept, _, _, _ = scipy.stats.linregress(x, y)
        _logger.debug('slope = %s', slope)
        _logger.debug('intercept = %s', intercept)
        _waterlevel_data[disc_gage][_PSERIES] = {}
        time = _current_time
        while time <= _end_time:
            waterlevel = (slope * (_hist_start - time).total_seconds() +
                          intercept)
            # Round waterlevel to 3 decimal places
            waterlevel = float("%.3f" % waterlevel)
            _waterlevel_data[disc_gage][_PSERIES][time] = waterlevel
            time += timedelta(minutes=interval)
    _logger.debug('_waterlevel_data[disc_gage][_PSERIES] = %s',
                  _waterlevel_data[disc_gage][_PSERIES])


def _rainfall_scenarios():
    # Get and apply artificial rainfall
    # NOTE: The basis for finding the appropriate rainfall scenario will be
    # based on the primary discharge gage which should be the first
    # discharge gage in the parameters file.
    _logger.info('Not raining now but it has rained in the past %s hours',
                 _RAIN_PAST_HOURS.seconds / (60 * 60))
    _logger.info('Applying rainfall scenario to watershed to prepare for \
HEC-HMS simulation...')
    # Get primary discharge gage
    disc_gage, disc_gage_info = _HECHMS_CONFIG.disc_gages.items()[0]
    _logger.info('Primary discharge gage = %s', disc_gage)
    interval = disc_gage_info['dss_info'].interval
    _logger.debug('interval = %s', interval)
    # Find latest baseflow
    _logger.info('Finding latest baseflow...')
    baseflow = _find_baseflow(_waterlevel_data[disc_gage][_ASERIES].items())
    _logger.warning('latest baseflow: %s', baseflow)
    bf_time, bf_value, bf_kernel = baseflow
    # Find latest baseflow in the results of the rain scenarios
    _logger.info('Finding latest baseflow in the results of the rain \
scenarios...')
    best = ()
    for scene_name, wr_data in _HECHMS_CONFIG.rainfall_scenarios.items():
        _logger.info('scene_name = %s', scene_name)
        (ht_diff, time, value,
         kernel) = _find_baseflow(wr_data['waterlevel'].items(), getbest=True,
                                  svalue=bf_value)
        best = (ht_diff, time, value, scene_name, kernel)
    _logger.debug('best = %s', best)
    # Construct artificial rainfall data
    _logger.info('Constructing artificial rainfall data...')
    rs_ht_diff, rs_time, rs_value, scene_name, rs_kernel = best
    artif_start = bf_time - rs_time
    _logger.debug('artif_start = %s', artif_start)
    artif_rain = {}
    for time_delta, rainfall in \
            sorted(_HECHMS_CONFIG.rainfall_scenarios[scene_name]['rainfall'].items()):
        artif_rain[artif_start + time_delta] = rainfall
    _logger.info('artif_rain = %s', artif_rain)
    # Check if start of artificial rain is earlier than simulation start
    global _start_time
    _logger.debug('_start_time = %s', _start_time)
    if artif_start < _start_time:
        if artif_start.minute % interval == 0:
            _start_time = artif_start
        else:
            new_min = (artif_start.minute / interval) * interval
            _start_time = datetime(artif_start.year,
                                   artif_start.month,
                                   artif_start.day,
                                   artif_start.hour,
                                   new_min)
        _logger.warning('New _start_time: %s', _start_time)
    # Add artificial rainfall to rainfall data
    new_rainfall_data = {}
    _logger.info('Adding artificial rainfall to _rainfall_data_in_mm...')
    for k, v in _rainfall_data_in_mm.items():
        new_rainfall_data[k] = copy.deepcopy(v)
        new_rainfall_data[k].update(artif_rain)
    _logger.debug('new_rainfall_data = %s', new_rainfall_data)
    # Update rainfall dss
    _update_rainfall_dss(new_rainfall_data)


def _find_baseflow(data, getbest=False, svalue=0.):
    # Sort data
    # If get best is True, sort ascending
    if getbest:
        sdata = sorted(data)
    else:
        # Else, sort descending
        sdata = sorted(data, reverse=True)
    candidates = []
    # Search data
    for i in range(len(sdata)):
        time, value = sdata[i]
        # Skip if current value is None
        if value is None:
            continue
        # Get samples up to search kernel size
        kernel = []
        half = (_BF_KERN_SIZE - 1) / 2
        for o in range(-half, half + 1, 1):
            if 0. <= i + o < len(sdata):
                _, v = sdata[i + o]
                if v is None:
                    break
                kernel.append(v)
            else:
                kernel.append(0.)
        # Skip if length of kernel is correct
        if len(kernel) != _BF_KERN_SIZE:
            continue
        # Also skip if water level is not descending
        if getbest:
            if kernel[0] < kernel[-1]:
                continue
        else:
            if kernel[0] > kernel[-1]:
                continue
        # If get best is True, add search value to kernel
        if getbest:
            kernel.append(svalue)
        _logger.debug('kernel = %s', kernel)
        ht_diff = max(kernel) - min(kernel)
        _logger.debug('ht_diff = %s', ht_diff)
        # If get best is True, add kernel to candidates
        if getbest:
            candidates.append([ht_diff, time, value, kernel])
        else:
            # If it is False, check if the difference in values is less than
            # the threshold
            if ht_diff <= _BF_HT_DIFF:
                return time, value, kernel
    # Sort candidates ascending and return the candidate with smallest height
    # difference
    return sorted(candidates)[0]


def _run_hechms():
    # Setup HEC-HMS first
    _logger.info('Initializing HEC-HMS...')
    interval = _initialize_hechms()
    # Run HEC-HMS
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
    # Get predicted data for each discharge gage
    _logger.info('Getting predicted data for each discharge gage...')
    for disc_gage, disc_gage_info in _HECHMS_CONFIG.disc_gages.items():
        _logger.info('Discharge gage: %s', disc_gage_info['base_series'])
        predicted_data = _get_discharge_from_dss(disc_gage, interval)
        # Convert discharge to water level and data to _waterlevel_data
        _waterlevel_data[disc_gage][_PSERIES] = {}
        xs = []
        ys = []
        for time, discharge in sorted(predicted_data.items()):
            # Check if time is a multiple of the discharge gage's interval
            if time.minute % disc_gage_info['dss_info'].interval == 0:
                if discharge > 0:
                    waterlevel = discharge2waterlevel(disc_gage_info,
                                                      discharge)
                else:
                    waterlevel = 0
                _waterlevel_data[disc_gage][_PSERIES][time] = waterlevel
                # Collect data for linear regression
                if (time <= _current_time and
                        time in _waterlevel_data[disc_gage][_ASERIES]):
                    xs.append(waterlevel)
                    actual = _waterlevel_data[disc_gage][_ASERIES][time]
                    ys.append(actual)
        _logger.debug('_waterlevel_data[disc_gage][_PSERIES] = %s',
                      _waterlevel_data[disc_gage][_PSERIES])
        # Check if length of xs and/or ys is at least 2
        _logger.debug('len(xs) = %s', len(xs))
        _logger.debug('xs = %s', xs)
        _logger.debug('len(ys) = %s', len(ys))
        _logger.debug('ys = %s', ys)
        if len(xs) >= 2 and len(ys) >= 2:
            _logger.info('Running linear regression on HEC-HMS output data...')
            # try:
            #     _run_linregress_on_hechms_data(disc_gage, interval, xs, ys)
            # except FloatingPointError:
            #     pass
            _run_linregress_with_outlier_removal(disc_gage, interval, xs, ys)


def _initialize_hechms():
    # Check if we have more than 1 discharge gage
    interval = _HECHMS_CONFIG.disc_gages.items()[0][1]['dss_info'].interval
    _logger.info('OLD interval = %s', interval)
    disc_gages_len = len(_HECHMS_CONFIG.disc_gages)
    if disc_gages_len > 1:
        _logger.warning('Multiple discharge gages! Getting GCD.')
        for i in range(1, disc_gages_len):
            interval0 = \
                _HECHMS_CONFIG.disc_gages.items()[i][1]['dss_info'].interval
            interval = fractions.gcd(interval, interval0)
        _logger.info('NEW interval = %s', interval)
    # Update control specs file
    global _start_time
    _logger.info('Updating control specs file...')
    _logger.debug('_start_time = %s', _start_time)
    _logger.debug('_end_time = %s', _end_time)
    _logger.debug('interval = %s', interval)
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
            buf.append('Time Interval: ' + str(interval))
        else:
            buf.append(line)
    # Write new control specs file
    with open(_HECHMS_CONFIG.ctrl_specs, 'w') as open_file:
        open_file.write('\n'.join(buf))
    # Update prec gages info in the time series data file
    _logger.info('Updating time series data file...')
    # Read current prec gages info from time series data file
    buf = []
    prec_gage = None
    for _, line in main_control.text_file_line_gen(_HECHMS_CONFIG.ts_data):
        if prec_gage:
            dss_file = _HECHMS_CONFIG.prec_gages[prec_gage]['dss_file']
            dss_info = _HECHMS_CONFIG.prec_gages[prec_gage]['dss_info']
            if 'Data Type' in line:
                buf.append('Data Type: ' + dss_info.type)
            elif 'Local to Project' in line:
                buf.append('Local to Project: NO')
            elif 'Start Time' in line:
                buf.append('Start Time: ' +
                           dss_info.start_time.strftime('%d %B %Y, %H:%M'))
            elif 'End Time' in line:
                buf.append('End Time: ' +
                           dss_info.end_time.strftime('%d %B %Y, %H:%M'))
            elif 'DSS File' in line:
                buf.append('DSS File: ' + op.realpath(dss_file))
            elif 'Pathname' in line:
                buf.append('Pathname: ' + dss_info.fullName)
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
    # Check if compute script is valid
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
    return interval


def _get_discharge_from_dss(disc_gage, interval):
    # Get discharge dss path/s
    disc_dss_paths = []
    t = _start_time
    t_last = _end_time + timedelta(days=1)
    while t <= t_last:
        logging.debug('t = %s', t)
        path_parts = ['',
                      '',
                      disc_gage,
                      'FLOW',
                      t.strftime('%d%b%Y').upper(),
                      str(interval) + 'MIN',
                      'RUN:' + str(_HECHMS_CONFIG.hechms_proj_name).upper(),
                      '']
        disc_dss_path = '/'.join(path_parts)
        disc_dss_paths.append(disc_dss_path)
        t += timedelta(days=1)
    _logger.debug('disc_dss_paths = %s', disc_dss_paths)
    # Get discharge from dss file
    _logger.info('Getting discharge from dss...')
    # Create dss handler input
    dss_handler_in = {'dss_file': _HECHMS_CONFIG.disc_dss_file_path,
                      'dss_paths': disc_dss_paths,
                      'start_time': _start_time,
                      'end_time': _end_time}
    output_file = repo_handler.dss_handler(
        dss_handler_in, ['read'], _MAIN_CONFIG)
    # Read output file
    predicted_data = pickle.load(open(output_file, 'rb'))
    # Delete output file
    os.remove(output_file)
    return predicted_data


def _run_linregress_on_hechms_data(disc_gage, interval, xs, ys):
    new_xs = []
    new_ys = []
    for x1, y1 in zip(xs, ys):
        if not new_xs and not new_ys:
            new_xs.append(x1)
            new_ys.append(y1)
            continue
        x0 = new_xs[-1]
        y0 = new_ys[-1]
        # Get diffs
        diff_x = x1 - x0
        diff_y = y1 - y0
        # If the differences have the same sign, add them to new xs and
        # ys
        if math.copysign(1, diff_x) == math.copysign(1, diff_y):
            new_xs.append(x1)
            new_ys.append(y1)
    _logger.debug('len(new_xs) = %s', len(new_xs))
    _logger.debug('new_xs = %s', new_xs)
    _logger.debug('len(new_ys) = %s', len(new_ys))
    _logger.debug('new_ys = %s', new_ys)
    # Check if length of new xs and/or ys is at least 2
    if not(len(new_xs) >= 2 and len(new_ys) >= 2):
        return
    # Get HEC-HMS output with linear regression
    x = np.array(new_xs)
    y = np.array(new_ys)
    try:
        slope, intercept, _, _, _ = scipy.stats.linregress(x, y)
    except FloatingPointError:
        _logger.debug('x: %s', x)
        _logger.debug('y: %s', y)
        raise
    _logger.debug('slope = %s', slope)
    _logger.debug('intercept = %s', intercept)

    if slope <= 0 or slope > 2:
        _logger.warning('Slope too high/low! %s', slope)

    if slope > 0:
        _waterlevel_data[disc_gage][_PLSERIES] = {}
        for time, waterlevel in \
                sorted(_waterlevel_data[disc_gage][_PSERIES].items()):
            waterlevel_linregress = slope * waterlevel + intercept
            _waterlevel_data[disc_gage][_PLSERIES][time] = \
                waterlevel_linregress
        # Get offset of predicted w/ linregress series to actual
        _get_predicted_offset(_PLSERIES, _PLOSERIES, disc_gage, interval)


def _run_linregress_with_outlier_removal(disc_gage, interval, _xs, _ys):

    _logger.debug('_xs = %s', _xs)
    _logger.debug('_ys = %s', _ys)

    # Compute linear regression
    slope, intercept, _, _, _ = scipy.stats.linregress(np.array(_xs),
                                                       np.array(_ys))
    _logger.info('slope = %s, intercept = %s', slope, intercept)

    # Remove outliers until slope becomes positive
    while slope < 0:

        # Compute square errors
        errors = []
        for x, y in zip(_xs, _ys):
            error = (slope * x + intercept) ** 2
            errors.append((error, x, y))

        # Sort errors
        errors.sort()

        _logger.info('Top 5 errors: %s', errors[-5:])

        # Remove top 5 largest errors
        errors = errors[:-5]

        # Repopulate _xs and _ys
        _xs = []
        _ys = []
        for _, x, y in errors:
            _xs.append(x)
            _ys.append(y)
        _logger.debug('_xs = %s', _xs)
        _logger.debug('_ys = %s', _ys)

        # Compute new slope and intercept
        slope, intercept, _, _, _ = scipy.stats.linregress(np.array(_xs),
                                                           np.array(_ys))
        _logger.info('slope = %s, intercept = %s', slope, intercept)

    # Apply final slope and intercept to all water level data
    _waterlevel_data[disc_gage][_PLSERIES] = {}
    for time, waterlevel in \
            sorted(_waterlevel_data[disc_gage][_PSERIES].items()):
        waterlevel_linregress = slope * waterlevel + intercept
        _waterlevel_data[disc_gage][_PLSERIES][time] = \
            waterlevel_linregress
    # Get offset of predicted w/ linregress series to actual
    _get_predicted_offset(_PLSERIES, _PLOSERIES, disc_gage, interval)


def _get_predicted_offset(src, dest, disc_gage, interval):
    # Get offset of src to actual water level and save src+offset to dest
    _waterlevel_data[disc_gage][dest] = {}
    offset = None
    for time, waterlevel in sorted(_waterlevel_data[disc_gage][src].items()):
        # for time, waterlevel in sorted(_waterlevel_data[disc_gage][src].items(),
        #                                reverse=True):
        if offset is None and time >= _current_time:
            # if offset is None and time >= _current_time - _SIM_PAST_HOURS:
            try:
                actual = _waterlevel_data[disc_gage][_ASERIES][time]
            except KeyError:
                # If actual water level is not available on the current
                # time, get the previous water level data
                _logger.warning('No actual water level on current time: %s',
                                time)
                actual = _find_prev_actual_waterlevel(disc_gage, interval,
                                                      time)
            offset = actual - waterlevel
        if offset:
            _waterlevel_data[disc_gage][dest][time] = waterlevel + offset
    _logger.debug('_waterlevel_data[disc_gage][dest] = %s',
                  _waterlevel_data[disc_gage][dest])


def _find_prev_actual_waterlevel(disc_gage, interval, time):
    # Finding previous time with actual water level data
    # Start test at time
    test = time

    _logger.debug(
        '_waterlevel_data[disc_gage][_ASERIES].keys(): %s',
        pprint.pformat(sorted(_waterlevel_data[disc_gage][_ASERIES].keys())))
    # _logger.debug('test not in _waterlevel_data[disc_gage][_ASERIES] = %s',
    #               test not in _waterlevel_data[disc_gage][_ASERIES])

    _logger.debug('_hist_start = %s', _hist_start)
    _logger.debug('test = %s', test)
    _logger.debug('test >= _hist_start = %s', test >= _hist_start)
    # Look for a time that is in the water level data and
    # the time must be greater than the start time
    # while (not test in _waterlevel_data[disc_gage][_ASERIES] and
    #        test >= _start_time):
    while test >= _hist_start:

        # Go back further in time
        test -= timedelta(minutes=interval)

        # test, _ = sorted(_waterlevel_data[disc_gage][_ASERIES].items(), reverse=True)[0]

        _logger.debug('test = %s', test)
        _logger.debug('test >= _hist_start = %s', test >= _hist_start)
        # Check if time is definitely in the water level data
        if test in _waterlevel_data[disc_gage][_ASERIES]:
            # Get actual water level at time
            actual = _waterlevel_data[disc_gage][_ASERIES][test]
            _logger.warning('Using: %s: %s', test, actual)
            return actual
        # else:

    # Raise an error if time is not found
    _logger.error('Cannot find previous time with actual water level \
data!')
    raise repo_handler.DataNotFoundError()


def _apply_tidal_correction(disc_gage, interval):
    _logger.info('Getting tidal prediction...')
    # Export actual water level data
    _logger.info('Exporting actual water level data...')
    wl_actual = 'water_level_actual.csv'
    _logger.debug('wl_actual = %s', wl_actual)
    with open(wl_actual, 'w') as open_file:
        for time, value in \
                sorted(_waterlevel_data[disc_gage][_ASERIES].items()):
            if time <= _current_time:
                open_file.write(str(time) + ' ' + str(value) + '\n')
    # Run TAPPY analysis
    # TAPPY
    # (http://sourceforge.net/apps/mediawiki/tappy/index.php?title=Main_Page)
    wl_def = op.join(_MAIN_CONFIG.install_dir, 'hec_tools', 'water_level.def')
    wl_xml = 'water_level.xml'
    _logger.debug('wl_def = %s', wl_def)
    _logger.debug('wl_xml = %s', wl_xml)
    _logger.info('Running TAPPY analysis...')
    tappya = subprocess.call(['tappy.py', 'analysis', wl_actual,
                              '--def_filename', wl_def, '--outputxml', wl_xml],
                             shell=True)
    if tappya != 0:
        _logger.error('Error while running tappy analysis! Exiting.')
        exit(1)
    # Run TAPPY prediction
    # Prediction length needs to be more than 13 hours as required by TAPPY
    tappy_time_fmt = '%Y-%m-%dT%H:%M:%S'
    start_date = _hist_start.strftime(tappy_time_fmt)
    end_date = _end_time.strftime(tappy_time_fmt)
    _logger.debug('start_date = %s', start_date)
    _logger.debug('end_date = %s', end_date)
    wl_predict = 'water_level_predict.csv'
    _logger.info('Running TAPPY prediction...')
    tappyp = subprocess.call(['tappy.py', 'prediction', wl_xml, start_date,
                              end_date, str(interval), '--fname', wl_predict],
                             shell=True)
    if tappyp != 0:
        _logger.error('Error while running tappy prediction! Exiting.')
        exit(1)
    # Read tidal prediction
    _logger.info('Reading and applying tidal prediction/correction...')
    _waterlevel_data[disc_gage][_TSERIES] = {}
    tide_sum = 0
    for _, line in main_control.text_file_line_gen(wl_predict):
        tokens = line.split()
        # Get time
        time = datetime.strptime(tokens[0], '%Y-%m-%dT%H:%M:%S')
        # Get tide
        tide = float(tokens[1])
        # Get tide sum
        tide_sum += tide
        # Set tide data
        _waterlevel_data[disc_gage][_TSERIES][time] = tide
    # Delete temporary files
    _logger.info('Deleting temporary files...')
    os.remove(wl_actual)
    os.remove(wl_xml)
    os.remove(wl_predict)
    tide_avg = tide_sum / float(len(_waterlevel_data[disc_gage][_TSERIES]))
    # Get predicted + tidal prediction - tide_average
    _logger.info('Getting predicted + tidal prediction - tide average \
series...')
    _waterlevel_data[disc_gage][_PTSERIES] = {}
    for time, predicted in _waterlevel_data[disc_gage][_PSERIES].items():
        if time in _waterlevel_data[disc_gage][_TSERIES]:
            tide = _waterlevel_data[disc_gage][_TSERIES][time]
            _waterlevel_data[disc_gage][_PTSERIES][time] = ((predicted + tide)
                                                            - tide_avg)
    # Get (predicted + tidal prediction - tide_average) offset to actual
    _logger.info('Getting the previous series offset to actual...')
    _get_predicted_offset(_PTSERIES, _PTOSERIES, disc_gage, interval)


def _get_release_trans(has_ran_hec_hms, disc_gage, disc_gage_info):
    release_trans = {_ASERIES: 'Actual',
                     _OPSERIES: _OPSERIES}
    # if has_ran_hec_hms:
    has_series = False
    for series_prio in disc_gage_info['pseries_prio']:
        _logger.debug('series_prio: %s', series_prio)
        if (series_prio == '_PSERIES' and
                _PSERIES in _waterlevel_data[disc_gage]):
            release_trans[_PSERIES] = 'Predicted'
            has_series = True
        elif (series_prio == '_POSERIES' and
              _POSERIES in _waterlevel_data[disc_gage]):
            release_trans[_POSERIES] = 'Predicted'
            has_series = True
        elif (series_prio == '_PLSERIES' and
              _PLSERIES in _waterlevel_data[disc_gage]):
            release_trans[_PLSERIES] = 'Predicted'
            has_series = True
        elif (series_prio == '_PLOSERIES' and
              _PLOSERIES in _waterlevel_data[disc_gage]):
            release_trans[_PLOSERIES] = 'Predicted'
            has_series = True
        elif (series_prio == '_PTSERIES' and
              _PTSERIES in _waterlevel_data[disc_gage]):
            release_trans[_PTSERIES] = 'Predicted'
            has_series = True
        elif (series_prio == '_PTOSERIES' and
              _PTOSERIES in _waterlevel_data[disc_gage]):
            release_trans[_PTOSERIES] = 'Predicted'
            has_series = True
        if has_series:
            break
    if not has_series:
        _logger.error('Matching priority predicted series not found!')
        _logger.error('Exiting.')
        exit(1)
    # else:
    #     release_trans[_POSERIES] = 'Predicted'
    return release_trans


def _get_avg_diffs(disc_gage, base_series):
    # Get all predicted series
    predict = [_PSERIES, _POSERIES,
               _PLSERIES, _PLOSERIES,
               _TSERIES, _PTSERIES, _PTOSERIES]
    _logger.debug('predict = %s', predict)
    avg_diffs = []
    # For each series
    for series in predict:
        if series in _waterlevel_data[disc_gage]:
            diffs = []
            # Get all actual and predicted water values for that series
            for time, actual_wl in \
                    sorted(_waterlevel_data[disc_gage][_ASERIES].items()):
                if (time >= _current_time and
                        time in _waterlevel_data[disc_gage][series]):
                    diffs.append(_waterlevel_data[disc_gage][series][time] -
                                 actual_wl)
            if len(diffs) == 0:
                avg_diffs.append('')
            else:
                avg_diffs.append('%.3f' % np.mean(diffs))
        else:
            avg_diffs.append('')
        if avg_diffs[-1]:
            _logger.info('%s: %s', series, avg_diffs[-1])
    # Write values to file
    filename = base_series.replace(' ', '_') + '_AVG_DIFF.txt'
    if not op.isfile(filename):
        with open(filename, 'w') as text_file:
            text_file.write('Date/Time')
            for series in predict:
                text_file.write(',' + series)
            text_file.write('\n')
    with open(filename, 'a') as text_file:
        text_file.write(str(_current_time) + ',' +
                        ','.join(map(str, avg_diffs)) + '\n')


def _export_predicted_data(disc_gage, disc_gage_info, release_trans):
    # Get previous fullname
    fullName = disc_gage_info['dss_info'].fullName
    _logger.debug('fullName = %s', fullName)
    # Split into tokens
    tokens = fullName.split('/')
    _logger.debug('tokens = %s', tokens)
    # Get interval
    interval = disc_gage_info['dss_info'].interval
    # Get sensor name
    sensor_name = tokens[2]
    # Construct raw data
    _logger.info('Constructing raw data...')
    raw_data = {'fullName': [tokens[1],
                             sensor_name,
                             'FLOW',
                             _current_time.strftime('%d%b%Y').upper(),
                             str(interval) + 'MIN',
                             'FORECAST'],
                'data': {sensor_name: {}},
                'units': 'm3/s',
                'type': 'INST-VAL'}
    # Get preferred predicted series
    _logger.info('Getting preferred predicted series...')
    pseries = [k
               for k, v in release_trans.items()
               if v == 'Predicted'][0]
    _logger.debug('pseries = %s', pseries)
    # Convert water level to discharge
    _logger.info('Converting water level to discharge...')
    end_time = None
    for time, waterlevel in \
            sorted(_waterlevel_data[disc_gage][pseries].items()):
        discharge = waterlevel2discharge(disc_gage_info, waterlevel)
        raw_data['data'][sensor_name][time] = float('%.4f' % discharge)
        end_time = time
    _logger.debug('raw_data = %s', raw_data)
    _logger.debug('end_time = %s', end_time)
    # Create dss handler input
    _logger.info('Creating dss handler input...')
    dss_handler_in = {'raw_data': raw_data,
                      'end_time': end_time,
                      'interval': interval}
    # Writing dss file
    _logger.info('Writing dss file...')
    output_file = repo_handler.dss_handler(dss_handler_in,
                                           ['write', '-s', 'csv'],
                                           _MAIN_CONFIG)
    # Read output file
    _logger.info('Reading input file...')
    dss_files, dss_info0 = pickle.load(open(output_file, 'rb'))
    dss_info = repo_handler.DSSInfo(*dss_info0)
    _logger.debug('dss_files = %s', dss_files)
    _logger.debug('dss_info = %s', dss_info)
    # Delete output file
    _logger.info('Deleting output file...')
    os.remove(output_file)
    return dss_files[0], dss_info


def _export_json(wl_name_base, release_trans, disc_wl_data):
    json_file_name = op.join(_MAIN_CONFIG.json_dir,
                             wl_name_base.replace(' ',
                                                  '_').replace(',', '').lower() + '.json')
    _logger.debug('disc_wl_data.keys() = %s', disc_wl_data.keys())
    for k, v1 in disc_wl_data.items():
        if k in release_trans and release_trans[k] == 'Predicted':
            v2 = {}
            for dt, wl in v1.items():
                v2[str(dt)] = wl
            json.dump(v2, open(json_file_name, 'w'), sort_keys=True, indent=4,
                      separators=(',', ': '))


def _import_predicted_json(wl_name_base, disc_wl_data):
    json_file_name = op.join(_MAIN_CONFIG.json_dir,
                             wl_name_base.replace(' ',
                                                  '_').replace(',',
                                                               '').lower() +
                             '_predicted.json')
    disc_wl_data[_OPSERIES] = {}
    if os.path.isfile(json_file_name):
        v2 = json.load(open(json_file_name, 'r'))
        for dt_str, wl in v2.items():
            dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
            disc_wl_data[_OPSERIES][dt] = wl


def _export_predicted_json(wl_name_base, release_trans, disc_wl_data):
    json_file_name = op.join(_MAIN_CONFIG.json_dir,
                             wl_name_base.replace(' ',
                                                  '_').replace(',',
                                                               '').lower() +
                             '_predicted.json')

    for k, v1 in disc_wl_data.items():
        if k in release_trans and release_trans[k] == 'Predicted':
            disc_wl_data[_OPSERIES][_current_time + timedelta(hours=1)] = v1[
                _current_time + timedelta(hours=1)]

    v2 = {}
    for dt, wl in disc_wl_data[_OPSERIES].items():
        if dt >= _current_time - _HIST_DAYS:
            v2[str(dt)] = wl
    json.dump(v2, open(json_file_name, 'w'), sort_keys=True, indent=4,
              separators=(',', ': '))

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
from hec.heclib.dss import HecDss
from hec.heclib.util import HecTime
from hec.io import TimeSeriesContainer
import argparse
import logging.handlers
import os
import os.path as op
import pickle
import sys

_version = '2.4'
_logger = logging.getLogger()
_LOG_LEVEL = logging.DEBUG
_CONS_LOG_LEVEL = logging.INFO
_FILE_LOG_LEVEL = logging.DEBUG
_DSS_BEGIN = datetime(1899, 12, 31)


def _read_dss():
    # Read data from dss
    open_file = HecDss.open(dss_file)
    data = {}
    for dss_path in dss_paths:
        # Get time series container from dss
        tsc = open_file.get(dss_path)
        for time0, value in zip(tsc.times, tsc.values):
            time = _DSS_BEGIN + timedelta(minutes=time0)
            # _logger.debug('%s: %s', time, value)
            # Get only data between start and end time
            if start_time <= time <= end_time:
                data[time] = value
    # Close dss file
    open_file.done()
    return data


def _write_dss_from_csv():
    # Write dss with data from csv
    dss_files = []
    for k, v in raw_data['data'].items():
        # Create time series container
        tsc = TimeSeriesContainer()
        # Construct full name
        fullName0 = raw_data['fullName'][:]
        fullName0[1] = k.upper()
        fullName = '/' + '/'.join(fullName0) + '/'
        tsc.fullName = fullName
        # Get start time
        start_time = sorted(v.keys())[0]
        start = HecTime(start_time.strftime('%d%b%Y'),
                        start_time.strftime('%H%M'))
        # Set interval
        tsc.interval = interval
        # Get list of times and respective values
        times = []
        values = []
        last_time = None
        key = datetime.strptime(start.dateAndTime().replace(
            '24:00', '0:00'), '%d %B %Y, %H:%M')
        while key <= end_time:
            value = v.pop(key, 'NO_DATA')
            _logger.debug('%s: %s', key, value)
            if value != 'NO_DATA':
                times.append(start.value())
                values.append(value)
                last_time = key
            start.add(tsc.interval)
            key = datetime.strptime(start.dateAndTime().replace(
                '24:00', '0:00'), '%d %B %Y, %H:%M')
        times.append(start.value())
        values.append(0.)
        # Set list of times, values, and size of list
        tsc.times = times
        tsc.values = values
        tsc.numberValues = len(values)
        _logger.debug('tsc.times: %s', tsc.times)
        _logger.debug('tsc.values: %s', tsc.values)
        # Set units
        tsc.units = raw_data['units']
        # Set type
#        type_ = 'PER-CUM'
        type_ = raw_data['type']
        tsc.type = type_
        # Write dss file
        dss_filename = '-'.join(fullName0[:3]).replace(' ', '_') + '.dss'
        _logger.debug('dss_filename = %s', dss_filename)
        _write_dss(dss_filename, tsc)
        dss_files.append(op.realpath(dss_filename))
        dss_info = type_, start_time, last_time, fullName, interval
    return dss_files, dss_info


def _write_dss(dss_filename, tsc):
    # Check if dss file already exists
    if op.isfile(dss_filename):
        _logger.warning('Deleting old file!')
        # Delete existing dss file
        try:
            os.remove(dss_filename)
        except OSError:
            _logger.warning('Warning! Deletion of old file failed.')
    else:
        _logger.warning("File doesn't exist!")
    # Write new dss file
    dss_file = HecDss.open(dss_filename)
    dss_file.put(tsc)
    dss_file.done()


def _update_dss():
    # Get start and end time
    sorted_data = sorted(data.keys())
    start_time = sorted_data[0]
    _logger.debug('start_time = %s', start_time)
    end_time = sorted_data[-1]
    _logger.debug('end_time = %s', end_time)
    # Get old time series container
    _logger.debug('dss_file = %s', dss_file)
    _logger.debug('dss_path = %s', dss_path)
    old_dss = HecDss.open(dss_file)
    old_tsc = old_dss.get(dss_path)
    old_dss.done()
    # Create a new time series container
    new_tsc = TimeSeriesContainer()
    # Copy properties from old
    new_tsc.fullName = old_tsc.fullName
    _logger.debug('new_tsc.fullName = %s', new_tsc.fullName)
    new_tsc.units = old_tsc.units
    _logger.debug('new_tsc.units = %s', new_tsc.units)
    new_tsc.type = old_tsc.type
    _logger.debug('new_tsc.type = %s', new_tsc.type)
    # Set interval
    new_tsc.interval = interval
    _logger.debug('new_tsc.interval = %s', new_tsc.interval)
    # Get start HecTime
    start = HecTime(start_time.strftime('%d%b%Y'), start_time.strftime('%H%M'))
    # Get new times and values
    times = []
    values = []
    key = datetime.strptime(start.dateAndTime(), '%d %B %Y, %H:%M')
    while key <= end_time:
        value = data.pop(key, 'NO_DATA')
        if value != 'NO_DATA':
            times.append(start.value())
            values.append(value)
        start.add(interval)
        key = datetime.strptime(start.dateAndTime(), '%d %B %Y, %H:%M')
    new_tsc.times = times
    new_tsc.values = values
    new_tsc.numberValues = len(values)
    # Write new dss file
    _write_dss(dss_file, new_tsc)

if __name__ == '__main__':
    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', action='version',
                        version=_version)
    parser.add_argument('-v', '--verbose', action='count')
    parser.add_argument('action', choices=['read', 'write', 'update'])
    parser.add_argument('-s', '--source', choices=['csv', 'dss'])
    parser.add_argument('-if', '--input_file')
    args = parser.parse_args()
    # Initialize logging
    _logger.setLevel(_LOG_LEVEL)
#    formatter = logging.Formatter('[%(asctime)s] %(filename)s\t: %(message)s')
    formatter = logging.Formatter('[%(asctime)s] %(filename)s \
(%(levelname)s,%(lineno)d)\t: %(message)s')
    if args.verbose >= 1:
        _CONS_LOG_LEVEL = logging.DEBUG
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(_CONS_LOG_LEVEL)
    ch.setFormatter(formatter)
    _logger.addHandler(ch)
    fh = logging.FileHandler(op.join('log', 'dss_handler.log'), mode='w')
    fh.setLevel(_FILE_LOG_LEVEL)
    fh.setFormatter(formatter)
    _logger.addHandler(fh)
    action = args.action
    source = args.source
    # Check if source is present if action is write
    if action == 'write' and source == None:
        _logger.error('Source cannot be None if action is write! Exiting.')
        exit(1)
    # Check if input file exists
    input_file = args.input_file
    if not op.exists(input_file):
        _logger.error('%s does not exist! Exiting.', input_file)
        exit(1)
    # Load dss handler input file
    dss_handler_in = pickle.load(open(input_file, 'rb'))
    # Read dss
    if action == 'read':
        _logger.info('Reading DSS file...')
        # Get arguments from input file
        try:
            dss_file = dss_handler_in['dss_file']
            dss_paths = dss_handler_in['dss_paths']
            start_time = dss_handler_in['start_time']
            end_time = dss_handler_in['end_time']
        except KeyError as e:
            _logger.exception(e)
            _logger.error('Incomplete data on the dss handler input file!')
            _logger.error('Exiting.')
            exit(1)
        _logger.debug('dss_file = %s', dss_file)
        _logger.debug('dss_paths = %s', dss_paths)
        _logger.debug('start_time = %s', start_time)
        _logger.debug('end_time = %s', end_time)
        # Read data from dss
        dss_handler_out = _read_dss()
    # Write dss
    elif action == 'write':
        _logger.info('Writing DSS file...')
        # Data from dss
        if source == 'dss':
            raise Exception('Not yet implemented.')
        # Data from csv
        elif source == 'csv':
            # Get data from input file
            try:
                raw_data = dss_handler_in['raw_data']
                end_time = dss_handler_in['end_time']
                interval = dss_handler_in['interval']
            except KeyError as e:
                _logger.exception(e)
                _logger.error('Incomplete data on the dss handler input file!')
                _logger.error('Exiting.')
                exit(1)
#            _logger.debug('source = %s', source)
#            _logger.debug('identifier = %s', identifier)
            _logger.debug('end_time = %s', end_time)
            _logger.debug('interval = %s', interval)
            # Write dss to file
            dss_handler_out = _write_dss_from_csv()
    # Update dss
    elif action == 'update':
        _logger.info('Updating DSS file...')
        # Get arguments from input file
        try:
            dss_file = dss_handler_in['dss_file']
            dss_path = dss_handler_in['dss_path']
            interval = dss_handler_in['interval']
            data = dss_handler_in['data']
        except KeyError as e:
            _logger.exception(e)
            _logger.error('Incomplete data on the dss handler input file!')
            _logger.error('Exiting.')
            exit(1)
        _logger.debug('dss_file = %s', dss_file)
        _logger.debug('dss_path = %s', dss_path)
        # Update data in the dss
        dss_handler_out = _update_dss()
    # _logger.debug('dss_handler_out = %s', dss_handler_out)
    # Get path for output file
    output_file = op.join(op.dirname(input_file), 'dss_handler.out')
    # Write output to file
    pickle.dump(dss_handler_out, open(output_file, 'wb'))
    # Shutdown logging
    logging.shutdown()

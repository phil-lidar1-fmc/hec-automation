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
import json

_logger = logging.getLogger()
_LOG_LEVEL = logging.DEBUG
_CONS_LOG_LEVEL = logging.INFO
_FILE_LOG_LEVEL = logging.DEBUG
_DSS_BEGIN = datetime(1899, 12, 31)


def _read_dss(input_):

    # Get data from input file
    try:
        dsspaths = input_['dsspaths']
        filepath = input_['filepath']
        start_time = input_['start_time']
        end_time = input_['end_time']
    except KeyError:
        _logger.exception('Incomplete data on the dss handler input file!')
        _logger.error('Exiting.')
        exit(1)
    _logger.debug('dsspaths: %s', dsspaths)
    _logger.debug('filepath: %s', filepath)
    _logger.debug('start_time: %s', start_time)
    _logger.debug('end_time: %s', end_time)

    # Open dss file
    dssfile = HecDss.open(filepath)

    # Read data from dss
    data = {}
    for dsspath in dsspaths:

        # Get time series container from dss
        tsc = dssfile.get(dsspath)

        for t0, value in zip(tsc.times, tsc.values):

            t = _DSS_BEGIN + timedelta(minutes=t0)
            _logger.debug('%s: %s', t, value)

            # Get only data between start and end time
            if start_time <= t <= end_time:
                data[t] = value

    # Close dss file
    dssfile.done()

    return data


def _write_dss(input_):

    # Create time series container
    tsc = TimeSeriesContainer()

    # Get data from input file
    try:
        tsc.fullName = input_['fullname']
        tsc.interval = input_['interval']
        tsc.units = input_['units']
        tsc.type = input_['dsstype']
        data = input_['data']
        filepath = input_['filepath']
    except KeyError:
        _logger.exception('Incomplete data on the dss handler input file!')
        _logger.error('Exiting.')
        exit(1)
    _logger.debug('filepath: %s', filepath)

    # Get list of times and respective values
    times = []
    values = []
    for k, v in sorted(data.viewitems()):
        # t = datetime.strptime(k, '%Y-%m-%d %H:%M:%S')
        t = HecTime(k.strftime('%d%b%Y'), k.strftime('%H%M'))
        times.append(t.value())
        values.append(v)

    # Set list of times, values, and size of list
    tsc.times = times
    tsc.values = values
    tsc.numberValues = len(values)
    _logger.debug('tsc.times: %s', tsc.times)
    _logger.debug('tsc.values: %s', tsc.values)

    # Check if dss file already exists
    if op.isfile(filepath):
        _logger.warning('Deleting old file!')
        # Delete existing dss file
        try:
            os.remove(filepath)
        except OSError:
            _logger.warning('Warning! Deletion of old file failed.')
    # else:
    #     _logger.warning("File doesn't exist!")
    # Write new dss file
    dss_file = HecDss.open(filepath)
    dss_file.put(tsc)
    dss_file.done()


if __name__ == '__main__':

    # print 'os.getcwd():', os.getcwd()

    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', action='version',
                        version=_version)
    parser.add_argument('-v', '--verbose', action='count')
    parser.add_argument('action', choices=['read', 'write'])
    # parser.add_argument('-s', '--source', choices=['csv', 'dss'])
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

    # Check if input file exists
    input_file = args.input_file
    if not op.exists(input_file):
        _logger.error('%s does not exist! Exiting.', input_file)
        exit(1)

    # Load dss handler input file
    input_ = pickle.load(open(input_file, 'rb'))

    # Read dss
    if args.action == 'read':
        _logger.info('Reading DSS file...')
        # # Get arguments from input file
        # try:
        #     dss_file = input_['dss_file']
        #     dss_paths = input_['dss_paths']
        #     start_time = input_['start_time']
        #     end_time = input_['end_time']
        # except KeyError as e:
        #     _logger.exception(e)
        #     _logger.error('Incomplete data on the dss handler input file!')
        #     _logger.error('Exiting.')
        #     exit(1)
        # _logger.debug('dss_file = %s', dss_file)
        # _logger.debug('dss_paths = %s', dss_paths)
        # _logger.debug('start_time = %s', start_time)
        # _logger.debug('end_time = %s', end_time)

        # Read data from dss
        output = _read_dss(input_)
        _logger.debug('output = %s', output)

        # Get path for output file
        output_file = op.join(op.dirname(input_file), 'dss_handler.out')
        # Write output to file
        pickle.dump(output, open(output_file, 'wb'))

    # Write dss
    elif args.action == 'write':
        _logger.info('Writing DSS file...')
        # Write dss to file
        _write_dss(input_)

    # Shutdown logging
    logging.shutdown()

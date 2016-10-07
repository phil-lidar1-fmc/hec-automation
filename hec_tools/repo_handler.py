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
import argparse
import collections
import copy
import errno
import logging
import os
import os.path as op
import pickle
import re
import socket
import subprocess
import time
import traceback
import urllib2
import main_control

_version = '2.11.1'
print(os.path.basename(__file__) + ': v' + _version)
_logger = logging.getLogger()
_logger.handlers.pop()
# _PREDICT_CSV_FIELDS = {'rainfall': 'rain_value(mm)',
#                        'waterlevel': 'waterlevel(m)'}
_PREDICT_CSV_FIELDS = {'rainfall': 'rain_value(mm)',
                       'waterlevel': 'waterlevel(MSL)(m)'}
_PREDICT_PARTC = {'rainfall': 'PRECIP-INC',
                  'waterlevel': 'WATER-LEVEL'}
_REPO = 'http://repo.pscigrid.gov.ph/'
_RETRY_TIMEOUT = 1
_RETRY_INTERVAL = 1
FDType = collections.namedtuple('FDType', ['file_type', 'data_type'])
FileEntry = collections.namedtuple('FileEntry', ['file_path', 'file_time'])
RepoID = collections.namedtuple('RepoID', ['source', 'fdtype', 'identifier'])
DSSInfo = collections.namedtuple('DSSInfo', ['type', 'start_time', 'end_time',
                                             'fullName', 'interval'])


class DataNotFoundError(Exception):
    pass


def dss_handler(dss_handler_in, opts, _MAIN_CONFIG):
    # Get input file path
    input_file = op.realpath('dss_handler.in')
    # Write dss handler input to file
    pickle.dump(dss_handler_in, open(input_file, 'wb'))
    # Get path to dss handler batch file
    dss_handler_bat = op.realpath(op.join(_MAIN_CONFIG.install_dir, 'dss_handler',
                                          'dss_handler.bat'))
    _logger.debug('dss_handler_bat = %s', dss_handler_bat)
    # # Get current path
    # current_path = os.getcwd()
    # # Check if dss_handler directory exists
    # dss_handler_dir = op.realpath(op.join('..', 'dss_handler'))
    # main_control.is_exists(dss_handler_dir)
    # os.chdir(dss_handler_dir)
    # Check if dss_handler.bat exists
    # dss_handler_bat = 'dss_handler.bat'
    main_control.is_exists(dss_handler_bat)
    command = [dss_handler_bat]
    for opt in opts:
        command.append(opt)
    command += ['-if', input_file]
    _logger.debug('command = %s', command)
    # Run dss_handler
    dss_handler = subprocess.call(command)
    if dss_handler != 0:
        _logger.error('Error while writing/reading to/from dss! Exiting.')
        exit(1)
    # # Return to current path
    # os.chdir(current_path)
    # Delete input file
    os.remove(input_file)
    # Get path of output file
    output_file = op.realpath('dss_handler.out')
    # Check if output file exists
    main_control.is_exists(output_file)
    return output_file


def get_data(repoID, start_time, cache_dir, no_cache, end_time=None,
             proxy=None):
    # Get arguments
    _logger.info('Getting parameters...')
    # Reset _urls
    global _urls
    _urls = None
    # Set global parameters
    global _source
    _source = repoID.source
    _logger.debug('_source = %s', _source)
    global _fdtype
    _fdtype = repoID.fdtype
    _logger.debug('_fdtype = %s', _fdtype)
    global _identifier
    _identifier = repoID.identifier
    _logger.debug('_identifier = %s', _identifier)
    global _start_time
    _start_time = start_time
    _logger.debug('_start_time = %s', _start_time)
    global _end_time
    if end_time:
        _end_time = end_time
    else:
        _end_time = datetime.now()
    _logger.debug('_end_time = %s', _end_time)
    global _cache_dir
    _cache_dir = cache_dir
    _logger.debug('_cache_dir = %s', _cache_dir)
    global _no_cache
    _no_cache = no_cache
    _logger.debug('_no_cache = %s', _no_cache)
    global _proxy
    _proxy = proxy
    _logger.debug('_proxy = %s', _proxy)
    # Fetch data
    _logger.info('Fetching data...')
    file_list = _fetch_data()
    _logger.debug('file_list = %s', file_list)
    # Read data
    _logger.info('Reading data...')
    # raw_data['data'][<sensor name>][<datetime>] = <value>
    raw_data = {'fullName': [], 'data': {}, 'units': ''}
    # Specify units and type
    if _fdtype.data_type == 'rainfall':
        raw_data['units'] = 'mm'
        raw_data['type'] = 'PER-CUM'
    elif _fdtype.data_type == 'waterlevel':
        raw_data['units'] = 'm'
        raw_data['type'] = 'INST-VAL'
    else:
        exc = ValueError('Illegal program state!')
        exc.values_dict = {'_fdtype': _fdtype}
        raise exc
    # Read each file in the list
    has_properties = False
    for file_path, _ in sorted(file_list):
        if file_path:
            # pabc
            if _source == 'pabc':
                raise Exception('Not yet supported.')
            # predict, csv
            elif (_source, _fdtype.file_type) == ('predict', 'csv'):
                # Read properties first if it hasn't been read
                if not has_properties:
                    (data, fullName,
                     _sensor_name) = _predict_csv_reader(file_path,
                                                         get_properties=True)
                    raw_data['fullName'] = fullName
                    has_properties = True
                # Else read data
                else:
                    data = _predict_csv_reader(file_path,
                                               sensor_name=_sensor_name)
                # Update raw data
                for k, v in data.items():
                    if not k in raw_data['data']:
                        raw_data['data'][k] = {}
                    raw_data['data'][k].update(v)
    _logger.debug('raw_data = {}'.format(raw_data))
    return raw_data


def get_dss(repoID, start_time, cache_dir, no_cache, _MAIN_CONFIG, end_time=None,
            sensor_name=None, proxy=None):
    # Get arguments
    file_type = repoID.fdtype.file_type
    # Get raw data from repo
    _logger.info('Getting raw data...')
    try:
        raw_data = get_data(repoID, start_time, cache_dir, no_cache,
                            end_time=end_time, proxy=proxy)
    except Exception as e:
        e.message += ('Error while reading data from repo!')
        raise
    # Process raw data from repo
    _logger.info('Processing raw data...')
    if len(raw_data['data']) == 0:
        raise Exception('Data not found!')
    # Create a deep copy of raw data
    raw_data_copy = copy.deepcopy(raw_data)
    # Detect time interval
    _logger.info('Getting time interval...')
    interval = get_time_interval(raw_data)
    # Write dss file
    _logger.info('Writing DSS file...')
    if file_type == 'csv':
        # Create dss handler input
        dss_handler_in = {'raw_data': raw_data,
                          'end_time': end_time,
                          'interval': interval}
        output_file = dss_handler(
            dss_handler_in, ['write', '-s', 'csv'], _MAIN_CONFIG)
        # Read output file
        dss_files, dss_info0 = pickle.load(open(output_file, 'rb'))
        dss_info = DSSInfo(*dss_info0)
        # Delete output file
        os.remove(output_file)
    elif file_type == 'dss':
        raise Exception('Not yet supported.')
    else:
        exc = ValueError('Illegal program state!')
        exc.values_dict = {'file_type': file_type}
        raise exc
    return dss_files, dss_info, raw_data_copy


def get_repoID(arg):
    tokens = arg.split('|')
    source = tokens[0]
    if not source in ['pabc', 'predict']:
        raise Exception('source must be either pabc or predict.')
    file_type = tokens[1]
    if not file_type in ['dss', 'csv']:
        raise Exception('file_type must be either dss or csv.')
    data_type = tokens[2]
    if not data_type in ['rainfall', 'waterlevel']:
        raise Exception('data_type must be either rainfall or waterlevel.')
    identifier = tokens[3]
    repoID = RepoID(source, FDType(file_type, data_type), identifier)
    return repoID


def get_time_interval(raw_data):
    # Hard-coding 10 minutes
    return 10

    time_diffs = []
    for _, v1 in raw_data['data'].items():
        old = None
        for k2, _ in sorted(v1.items()):
            if old:
                time_diffs.append((k2 - old).seconds / 60)
            old = k2
    return collections.Counter(time_diffs).most_common(1)[0][0]


def id_format(id_):
    _logger.debug("id_.split('-'): %s", id_.split('-'))
    tokens = id_.split('-')
    place = '-'.join(tokens[1:-1]).replace('_', ' ')
    _logger.debug('place = %s', place)
    return place


def _fetch_content(url):
    url_escaped = url.replace(',', '%2c').replace('&', '%26')
    url_success = False
    retries = 0
    # Retry until succcesful access to the url or until timeout is
    # reached
    while retries < _RETRY_TIMEOUT and not url_success:
        try:
            # Construct request
            if _no_cache:
                req = urllib2.Request(url=url_escaped,
                                      headers={'Cache-Control': 'no-cache',
                                               'Pragma': 'no-cache'})
            else:
                req = urllib2.Request(url=url_escaped)
            # Open socket with request
            sock = urllib2.urlopen(req)
            # If succesful, set url_success to True
            url_success = True
            # Read content from socket
            content = sock.read()
            # Close the socket
            sock.close()
        except (urllib2.URLError, socket.error) as _:
            _logger.warning('Retrying...')
            # Sleep for the specified retry interval
            time.sleep(_RETRY_INTERVAL)
            # Increment number of retries
            retries += 1
    # If succesfully connected
    if url_success:
        # return content
        return content
    # If not
    else:
        # Raise an error
        _logger.error('Cannot connect to %s !', url_escaped)
        raise DataNotFoundError


def _fetch_data():
    # Generate urls
    _logger.info('Generating urls...')
    global _urls
    # Check if we already have a list of urls
    _logger.debug('_urls is None: %s', _urls is None)
    if _urls is None:
        # If we don't have a list of urls: _source, _fdtype,
        # _identifier, _start_time and _end_time must not be None
        _logger.debug('all([_source, _fdtype, _identifier, _start_time, \
_end_time] = %s', all([_source, _fdtype, _identifier, _start_time, _end_time]))
        if all([_source, _fdtype, _identifier, _start_time, _end_time]):
            _logger.debug('_source = %s', _source)
            _logger.debug('_fdtype = %s', _fdtype)
            _logger.debug('_identifier = %s', _identifier)
            _logger.debug('_start_time = %s', _start_time)
            _logger.debug('_end_time = %s', _end_time)
            # Generate url list
            _urls = {}
            # predict:dss
            if (_source, _fdtype.file_type) == ('predict', 'dss'):
                url = _REPO + _source + '/dss/' + _identifier + '.dss'
                _urls[url] = None
            # csv
            else:
                # predict
                if _source == 'predict':
                    # New files in the predict:csv folder are created hourly
                    file_interval = timedelta(hours=1)
                # pabc
                elif _source == 'pabc':
                    # New files in the pabc folder are created daily
                    file_interval = timedelta(days=1)
                # Loop from the _start_time till the _end_time
                file_time = _start_time
                while file_time <= _end_time:
                    # Get year, month, day, hour from datetime
                    year = str(file_time.year)
                    month = str(file_time.month).zfill(2)
                    day = str(file_time.day).zfill(2)
                    hour = str(file_time.hour).zfill(2)
                    # pabc:waterlevel
                    if (_source, _fdtype.data_type) == ('pabc', 'waterlevel'):
                        url = (_REPO + _source + '/' + _identifier +
                               '/WATERLEVEL/' + year + '/' + month + '/' +
                               day + '/Waterlevel' + hour + '.csv')
                    # pabc:rainfall
                    elif (_source, _fdtype.data_type) == ('pabc', 'rainfall'):
                        url = (_REPO + _source + '/' + _identifier +
                               '/RAINFALL/' + year + '/' + month + '/' + day +
                               '/' + 'Rainfall' + hour + '.csv')
                    # predict
                    elif _source == 'predict':
                        url = (_REPO + _source + '/' + year + '/' +
                               month + '/' + day + '/' + _identifier + '-' +
                               year + month + day + '.csv')
                    # Add url to dict
                    _urls[url] = file_time
                    # Increment file_time by file_interval
                    file_time += file_interval
        else:
            raise Exception('Incomplete parameters. Check your arguments.')
    # Check if we indeed have _urls in the list
    if len(_urls) == 0:
        raise Exception('Url list is empty.')
    _logger.debug('_urls = %s', _urls)
    # Setup _proxy
    proxy_handler = urllib2.ProxyHandler(_proxy)
    urllib2.install_opener(urllib2.build_opener(proxy_handler))
    # Fetch data in each url
    file_list = []
    _logger.info('Processing urls...')
    counter = len(_urls)
    for url, file_time in sorted(_urls.items()):
        # Get path of file in _cache
        file_path = op.join(_cache_dir,
                            url.replace(_REPO, '').replace('/', os.sep))
        _logger.debug('file_path = %s', file_path)
        # Get url if _no_cache is True and it is the last file
        # or if the file doesn't exist in the _cache
        last_file = counter == 1 and _no_cache
        if last_file or not (op.isfile(file_path) and op.getsize(file_path) > 0):
            file_path = _process_url(file_path, url, last_file)
        # Add file path to list
        file_list.append(FileEntry(file_path, file_time))
        # Decrease counter
        counter -= 1
    return file_list


def _get_ir_block_length():
    delta = _end_time - _start_time
    if delta < timedelta(days=1):
        return 'IR-DAY'
    elif delta < timedelta(days=30):
        return 'IR-MONTH'
    elif delta < timedelta(days=365):
        return 'IR-YEAR'
    elif delta < timedelta(days=3650):
        return 'IR-DECADE'
    else:
        return 'IR-CENTURY'
    # if _end_time.year - _start_time.year >= 1:
        # return 'IR-DECADE'
    # elif _end_time.month - _start_time.month >= 1:
        # return 'IR-YEAR'
    # elif _end_time.day - _start_time.day >= 1:
        # return 'IR-MONTH'
    # else:
        # return 'IR-DAY'


def _mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and op.isdir(path):
            pass
        else:
            raise


def _predict_csv_reader(csv_file, get_properties=False, sensor_name=None):
    fullName = []
    data = {}
    field_id = -1
    # Read each line of the csv file
    for line_num, line in main_control.text_file_line_gen(csv_file):
        # Get properties for fullName (dss)
        if get_properties and line_num < 8:
            tokens = line.split()
            if 'province' in line:
                # Part A
                fullName.append('_'.join(tokens[1:]).upper())
            elif 'location' in line:
                # Part B
                fullName.append('')
                sensor_name = '_'.join(tokens[1:]).upper()
                # Part C
                fullName.append(_PREDICT_PARTC[_fdtype.data_type])
                # Part D
                fullName.append('')
                # Part E
                fullName.append(_get_ir_block_length())
                # Part F
                fullName.append('OBS')
        # Get column number of desired data type
        elif line_num == 8:
            tokens = line.split(',')
            try:
                field_id = tokens.index(_PREDICT_CSV_FIELDS[_fdtype.data_type])
            except IndexError as e:
                # Try MSL waterlevel first for sensors which they exist
                # Fallback to normal if they don't
                _logger.exception(e)
                if _PREDICT_CSV_FIELDS[_fdtype.data_type] == 'waterlevel(MSL)(m)':
                    field_id = tokens.index('waterlevel(m)')
                else:
                    _logger.error('_fdtype.data_type = %s', _fdtype.data_type)
                    _logger.error('tokens = %s', tokens)
                    raise
        # Get data
        elif line_num > 8:
            # Read data
            tokens = line.split(',')
            time_tokens = re.split(r'[- :]', tokens[0])[:-1]
            # Round down minutes to the nearest multiple of 10
            time_tokens[-1] = (int(time_tokens[-1]) / 10) * 10
            data_time = datetime(*[int(t) for t in time_tokens])
            if _start_time <= data_time <= _end_time:
                try:
                    # Workaround for missing "waterlevel(MSL)(m)",
                    # use "waterlevel(m)" which is the previous field
                    if tokens[field_id] == '':
                        field_id -= 1
                    data_value = float(tokens[field_id])
                    # Store data
                    if not sensor_name in data:
                        data[sensor_name] = {}
                    # _logger.info("sensor_name = %s", sensor_name)
                    # _logger.info(_PREDICT_CSV_FIELDS[_fdtype.data_type])
                    data[sensor_name][data_time] = data_value
                except ValueError:
                    pass
    # Check if to get properties
    if get_properties:
        return data, fullName, sensor_name
    else:
        return data


def _process_url(path, url, last_file):
    _logger.info('Fetching data from repo...')
    # Check if url exists
#    if _url_exists(url):
    try:
        content = _fetch_content(url)
        # Check if local directory exists
        dir_path = op.dirname(path)
        if not op.isdir(dir_path):
            # Create the local directory if it doesn't
            _mkdir_p(dir_path)
        # Write content to file
        with open(path, 'wb') as local_file:
            local_file.write(content)
        return path
    except DataNotFoundError:
        if last_file:
            _logger.error('Also the last file, re-raising error.')
            raise
#    else:
#        _logger.warning('%s not found!', url)
#        if last_file:
#            _logger.error('Also the last file, raising error.')
#            raise DataNotFoundError()


def _url_exists(url):
    url_dir, filename = op.split(url)
    content = _fetch_content(url_dir)
    return content.find(filename.replace('&', '&amp;')) > -1

if __name__ == '__main__':

    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--version', action='version',
                        version=_version)
    parser.add_argument('-rid', '--repoID', required=True)
    parser.add_argument('-st', '--start_time', required=True)
    parser.add_argument('-et', '--end_time')
    parser.add_argument('-sn', '--sensor_name')
    parser.add_argument('-cd', '--cache_dir',
                        default='C:\\workspace\\.asti_repo_cache')
    parser.add_argument('-p', '--proxy')
    args = parser.parse_args()
#    if _verbose: print _header(), args

    # Parse repoID
    try:
        repoID = get_repoID(args.repoID)
    except Exception:
        print 'Error parsing repoID! Exiting.'
        exit(1)
#    if _verbose: print _header(), 'repoID =', repoID

    # Parse start and end time
    try:
        start_time = datetime.strptime(args.start_time,
                                       '%Y-%m-%d_%H:%M')
    except ValueError:
        #        print _header(), 'Error while parsing start time! Exiting.'
        exit(1)
#    if _verbose: print _header(), 'start_time =', start_time
    try:
        end_time = datetime.strptime(args.end_time,
                                     '%Y-%m-%d_%H:%M')
    except ValueError:
        #        print _header(), 'Error while parsing end time! Exiting.'
        exit(1)
#    if _verbose: print _header(), 'end_time =', end_time

    # Get cache directory and proxy settings
    if args.cache_dir:
        # Get cache directory path and check if it exists
        cache_dir = op.realpath(args.cache_dir)
        main_control.is_exists(cache_dir, op.basename(__file__))
#        if _verbose: print _header(), 'cache_dir', cache_dir
    proxy = None
    if args.proxy:
        proxy = {'http': args.proxy}
#        if _verbose: print _header(), 'proxy =', proxy

    try:
        get_dss(repoID, start_time, cache_dir, _MAIN_CONTROL, proxy=proxy, end_time=end_time,
                sensor_name=args.sensor_name)
    except ValueError as e:
        #        print _header(), e.message
        #        print e.values_dict
        traceback.print_exc()
#        print _header(), 'Exiting.'
        exit(1)
    except Exception as e:
        #        print _header(), e.message
        traceback.print_exc()
#        print _header(), 'Exiting.'
        exit(1)

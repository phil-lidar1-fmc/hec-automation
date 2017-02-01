'''
Copyright (c) 2017, Kenneth Langga (klangga@gmail.com)
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

from datetime import timedelta
from pprint import pprint
import json
import os
import pickle
import subprocess
import traceback


class DSSFile:

    def __init__(self, filename=None):

        # Initialize
        self._dsstype = ''
        self._start_time = None
        self._end_time = None
        self._fullname = ['' for _ in xrange(6)]
        self._interval = 10  # minutes
        self._filepath = ''
        self._sensor = None
        # print 'o:', o

        # if o:
        #     # print 'isinstance(o, ASTISensor):', isinstance(o, ASTISensor)
        #     from asti_sensor import ASTISensor
        #     if isinstance(o, str):
        # filename = o

        if filename:

            # Get absolute path
            filepath = os.path.abspath(filename)

            # Check if filepath exists
            if os.path.isfile(filepath):
                self._filepath = filepath

            # elif isinstance(o, ASTISensor):
            #     self._sensor = o

    def _sanitize(self, t):
        return t.replace(' ', '_').replace(',', '').upper()

    def read(self, dsspaths):

        # Create input file
        input_ = {
            'dsspaths': dsspaths,
            'filepath': self._filepath,
            'start_time': self._start_time,
            'end_time': self._end_time,
        }

        # Read dss file
        self.dss_handler('read', input_)

    def write(self):

        # Get filepath
        filename = '-'.join(self._fullname[:3]) + '.dss'
        self._filepath = os.path.abspath(filename)

        # Create input file
        input_ = {
            'data': self._data,
            'dsstype': self._dsstype,
            'filepath': self._filepath,
            'fullname': self.fullname(),
            'interval': self._interval,
            'units': self._units
        }

        # Write dss file
        self.dss_handler('write', input_)

        # return self

    def fullname(self, fullname_=None):
        if fullname_:
            self._fullname = fullname_
        else:
            return '/' + '/'.join(self._fullname) + '/'

    def dss_handler(self, action, input_):

        # Dump input data to json
        input_fp = os.path.abspath('dss_handler.in')
        pickle.dump(input_, open(input_fp, 'wb'))

        # Get batch file path
        hectools_dir = os.path.split(os.path.abspath(__file__))[0]
        install_dir = os.path.split(hectools_dir)[0]
        dss_handler_bat = os.path.join(install_dir, 'dss_handler',
                                       'dss_handler.bat')

        # Check if batch file exists
        if not os.path.isfile(dss_handler_bat):
            print f, 'does not exist! Exiting.'
            exit(1)

        # Get appropriate args
        cmd = [dss_handler_bat]
        if action == 'write':
            cmd += ['write']
        elif action == 'read':
            cmd += ['read']
        cmd += ['-if', input_fp]

        # Run dss_handler.bat
        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError:
            print 'Error while writing/reading to/from dss! Exiting.'
            traceback.print_exc()
            exit(1)

        # Delete input file
        os.remove(input_fp)

        # Get output data
        output_fp = os.path.abspath('dss_handler.out')
        output = None
        if os.path.isfile(output_fp):
            output = pickle.load(open(output_fp, 'rb'))
        self._data = output

    def filepath(self):
        return self._filepath

    def sensor(self, sensor_=None):
        if sensor_:
            self._sensor = sensor_
            self._data = self._sensor.data()
            self._start_time = self._sensor.start_time()
            self._end_time = self._sensor.end_time()
            self._units = self._sensor.units()

            #
            # Get full name
            #
            # Part A
            self._fullname[0] = self._sanitize(self._sensor.meta()['province'])

            # Part B
            self._fullname[1] = self._sanitize(self._sensor.meta()['location'])

            # Part C
            if 'waterlevel' in self._sensor.data_type():
                self._fullname[2] = 'WATER-LEVEL'
                self._dsstype = 'INST-VAL'
            elif 'rain_value' in self._sensor.data_type():
                self._fullname[2] = 'PRECIP-INC'
                self._dsstype = 'PER-CUM'

            # Part E
            delta = self._end_time - self._start_time
            if delta < timedelta(days=1):
                self._fullname[4] = 'IR-DAY'
            elif delta < timedelta(days=30):
                self._fullname[4] = 'IR-MONTH'
            elif delta < timedelta(days=365):
                self._fullname[4] = 'IR-YEAR'
            elif delta < timedelta(days=3650):
                self._fullname[4] = 'IR-DECADE'
            else:
                self._fullname[4] = 'IR-CENTURY'

            # Part F
            self._fullname[5] = 'OBS'

        else:
            return self._sensor

    def dsstype(self, dsstype_=None):
        if dsstype_:
            self._dsstype = dsstype_
        else:
            return self._dsstype

    def start_time(self, start_time_=None):
        if start_time_:
            self._start_time = start_time_
        else:
            return self._start_time

    def end_time(self, end_time_=None):
        if end_time_:
            self._end_time = end_time_
        else:
            return self._end_time

    def data(self, data_=None):
        if data_:
            self._data = data_
        else:
            return self._data

    def units(self, units_=None):
        if units_:
            self._units = units_
        else:
            return self._units

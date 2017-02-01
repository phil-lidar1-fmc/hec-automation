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

from datetime import datetime, timedelta
from dss_file import DSSFile
from pprint import pprint, pformat
import requests


class ASTISensor:
    _API_URL = 'http://weather.asti.dost.gov.ph/web-api/index.php/api/data/'
    _USER = 'noahdream'
    _PASS = 'no@hDr3am1116'
    _INTERVAL = 10  # Fix interval to 10mins

    def __init__(self, dev_id=None):

        # Initialize
        self._data = {}
        self._meta = {}
        self._start_time = None
        self._end_time = None
        self._data_type = ''
        self._dss = None

        if dev_id:
            self._dev_id = str(dev_id)
            self._dev_url = self._API_URL + self._dev_id
            r = requests.get(self._dev_url, auth=(self._USER, self._PASS))
            if r.status_code == 200:
                c = r.json()
                for k in c:
                    if k != 'data':
                        self._meta[k] = c[k]

    def fetch_data(self, start_time=None, end_time=None):
        url = self._dev_url
        if start_time:
            url += '/from/' + start_time.strftime('%Y-%m-%d')
        if end_time:
            url += '/to/' + end_time.strftime('%Y-%m-%d')
        r = requests.get(url, auth=(self._USER, self._PASS))
        if r.status_code == 200:
            for e in r.json()['data']:
                dateTime = e['dateTimeRead'][:-3]
                utcOffset = e['dateTimeRead'][-3:]
                dt = datetime.strptime(dateTime,
                                       '%Y-%m-%d %H:%M:%S')
                # Round down minutes to the nearest interval multiple
                mins = dt.minute / self._INTERVAL * self._INTERVAL
                # Ignore seconds
                dateTimeRead = datetime(year=dt.year,
                                        month=dt.month,
                                        day=dt.day,
                                        hour=dt.hour,
                                        minute=mins)
                # Skip values outside range
                if start_time and dateTimeRead < start_time:
                    continue
                if end_time and dateTimeRead > end_time:
                    continue
                for k, v in e.viewitems():
                    if k != 'dateTimeRead':
                        if k not in self._data:
                            self._data[k] = {}
                        # if dateTimeRead not in self._data[k]:
                        #     self._data[k][dateTimeRead] = {}
                        try:
                            self._data[k][dateTimeRead] = float(v)
                        except TypeError:
                            # Ignore null values
                            continue
                        # Convert cm to m for waterlevel
                        if 'waterlevel' in k:
                            self._data[k][dateTimeRead] /= 100.
            # Get start time and end time
            data_type = self._data.keys()[0]
            sorted_data = sorted(self._data[data_type].viewitems())
            self._start_time = sorted_data[0][0]
            self._end_time = sorted_data[-1][0]

    def data_type(self, data_type_=None):
        if data_type_:
            # if data_type_ in self._data:
            self._data_type = data_type_
            # else:
            #     raise Exception('Data type not found!')
        else:
            return self._data_type

    def dss(self):
        if self._dss is None:
            self._dss = DSSFile()
            self._dss.sensor(self)
            self._dss.write()

        return self._dss

    def data(self):
        if self._data_type not in self._data:
            if 'waterlevel' in self._data_type:
                return
            else:
                raise Exception('Data type not found!')
        return self._data[self._data_type]

    def meta(self):
        return self._meta

    def units(self):
        if 'waterlevel' in self._data_type:
            return 'm'
        elif 'rain_value' in self._data_type:
            return 'mm'

    def start_time(self):
        return self._start_time

    def end_time(self):
        return self._end_time

    def __str__(self):
        return pformat({
            'dev_url': self._dev_url,
            'meta': self._meta,
            'data': self._data
        })

    def __repr__(self):
        return pformat({
            'dev_url': self._dev_url,
            'meta': self._meta,
            'data': self._data
        })

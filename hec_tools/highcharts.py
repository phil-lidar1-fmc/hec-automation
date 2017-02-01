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

from pprint import pformat
import os
import os.path as op
import logging

_logger = logging.getLogger()


def _sanitize(t):
    return t.replace(' ', '_').replace(',', '').upper()


def write_chart(current_time, start_time, end_time,
                release_trans, disc_gage_info, main_config, hechms_config):

    # Water level and rainfall combined in one chart

    # Set global parameters
    global _current_time
    _current_time = current_time

    global _start_time
    _start_time = start_time

    global _end_time
    _end_time = end_time

    global _release_trans
    _release_trans = release_trans

    global _disc_gage_info
    _disc_gage_info = disc_gage_info

    global _MAIN_CONFIG
    _MAIN_CONFIG = main_config

    global _HECHMS_CONFIG
    _HECHMS_CONFIG = hechms_config

    global _location
    _location = _disc_gage_info['sensor'].meta()['location']

    global _ismsl
    _ismsl = 'non-MSL'
    if 'msl' in _disc_gage_info['sensor'].data_type():
        _ismsl = 'MSL'

    # Get chart file path
    chart_fp = op.join(_MAIN_CONFIG.charts_dir,
                       _sanitize(_location) + '_' + _ismsl)

    # If live, write the release and the debug chart
    write_html(chart_fp + '.html')
    write_html(chart_fp + '_pagasa.html', show_old_predicted=True)
    write_html(chart_fp + '_debug.html', testing=True,
               show_old_predicted=True)


def write_html(chart_fp, testing=False, show_old_predicted=False):

    # Write chart html file
    _logger.info('Writing chart: %s', chart_fp)
    with open(chart_fp, 'w') as chart_file:

        chart_file.write("""
<!DOCTYPE HTML>
<html>
    <head>
        <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
        <title>""")

        chart_file.write(_location + ' (' + _ismsl + ') @' +
                         str(_current_time))

        chart_file.write("""</title>
        <script type="text/javascript" \
src="js/jquery.1.8.2.min.js"></script>
        <script type="text/javascript">
$(function () {
        $('#container').highcharts('StockChart', {
            chart: {
                zoomType: 'x'
            },""")

        chart_file.write("""
            legend: {
                enabled: true
            },
            rangeSelector: {
                selected: 5,
                buttons: [{
                    type: 'hour',
                    count: 1,
                    text: '1h'
                }, {
                    type: 'hour',
                    count: 3,
                    text: '3h'
                }, {
                    type: 'hour',
                    count: 6,
                    text: '6h'
                }, {
                    type: 'hour',
                    count: 12,
                    text: '12h'
                }, {
                    type: 'day',
                    count: 1,
                    text: '1d'
                }, {
                    type: 'day',
                    count: 3,
                    text: '3d'
                }, {
                    type: 'day',
                    count: 6,
                    text: '6d'
                }, {
                    type: 'day',
                    count: 12,
                    text: '12d'
                }]
            },
            plotOptions: {
                series: {
                    dataGrouping: {
                        enabled: false
                    }
                }
            },
            title: {
                text: """)

        chart_file.write("'" + _location + ' (' + _ismsl + ') @' +
                         str(_current_time) + "'")

        chart_file.write("""
            }""")

        chart_file.write(""",
            xAxis: {
                ordinal: false,
                type: 'datetime',
                plotBands: [{ // Predicted
                    from: """)

        chart_file.write(_utc_format(_current_time))

        chart_file.write(""",
                    to: """)

        chart_file.write(_utc_format(_end_time))

        chart_file.write(""",
                    label: {
                        text: 'Predicted',
                        verticalAlign : 'top',
                        align: 'left',
                        rotation: 90,
                        x: 5
                    }
                }, { // Actual
                    color: '#FCFFC5',
                    from: """)

        chart_file.write(_utc_format(_start_time))

        chart_file.write(""",
                    to: """)

        chart_file.write(_utc_format(_current_time))

        chart_file.write(""",
                    label: {
                        text: 'Actual',
                        verticalAlign : 'top',
                        align: 'right',
                        rotation: 270,
                        x: -5
                    }
                }]
            }""")

        chart_file.write(""",
            yAxis: [{ // Primary Axis (Water Level)
                labels: {
                    formatter: function() {
                        return this.value +' m';
                    },
                    style: {
                        color: '#AA4643'
                    }
                },
                title: {
                    text: 'Water Level',
                    style: {
                        color: '#AA4643'
                    }
                }""")

        if 'min_waterlevel' in _disc_gage_info['chart_options']:
            chart_file.write("""
                , min: """ +
                             str(_disc_gage_info['chart_options']['min_waterlevel']))

        if 'max_waterlevel' in _disc_gage_info['chart_options']:
            chart_file.write("""
                , max: """ +
                             str(_disc_gage_info['chart_options']['max_waterlevel']))

        if 'spilling_levels' in _disc_gage_info:
            chart_file.write("""
                , plotLines: [{
                    color: 'green',
                    dashStyle: 'longdashdot',
                    width: 2,
                    value: """ + str(_disc_gage_info['spilling_levels']['left_bank']) + """,
                    label : {
                        text: 'Left bank',
                        align: 'left',
                        verticalAlign: 'top',
                        x: -60,
                        y: 10
                    }
                }, {
                    color: 'blue',
                    dashStyle: 'longdashdot',
                    width: 2,
                    value: """ + str(_disc_gage_info['spilling_levels']['right_bank']) + """,
                    label : {
                        text: 'Right bank',
                        align: 'left',
                        verticalAlign: 'top',
                        x: -60,
                        y: 10
                    }
                }]
                """)

        chart_file.write("""
            }, { // Secondary Axis (Rainfall)
                title: {
                    text: 'Rainfall',
                    style: {
                        color: '#4572A7'
                    }
                },
                labels: {
                    formatter: function() {
                        return this.value +' mm';
                    },
                    style: {
                        color: '#4572A7'
                    },
                    y: 12
                },
                reversed: true,
                opposite: true,
                min: 0,""")

        chart_file.write("""
                minorGridLineWidth: 0,
                gridLineWidth: 0,
                alternateGridColor: null,
                plotBands: [{ // Light
                    from: 0,
                    to: 2.5,
                    color: 'rgba(63, 210, 217, 0.1)',
                    label: {
                        text: 'Light',
                        align: 'right',
                        verticalAlign: 'top',
                        x: -60,
                        y: 10
                    }
                }, { // Moderate
                    from: 2.5,
                    to: 7.5,
                    color: 'rgba(71, 114, 252, 0.1)',
                    label: {
                        text: 'Moderate',
                        align: 'right',
                        verticalAlign: 'top',
                        x: -60,
                        y: 10
                    }
                }, { // Heavy
                    from: 7.5,
                    to: 15,
                    color: 'rgba(64, 63, 199, 0.1)',
                    label: {
                        text: 'Heavy',
                        align: 'right',
                        verticalAlign: 'top',
                        x: -60,
                        y: 10
                    }""")

        chart_file.write("""
                }, { // Intense
                    from: 15,
                    to: 30,
                    color: 'rgba(254, 195, 75, 0.1)',
                    label: {
                        text: 'Intense',
                        align: 'right',
                        verticalAlign: 'top',
                        x: 60,
                        y: -10
                    }""")

        chart_file.write("""
                }, { // Torrential
                    from: 30,
                    to: 9999,
                    color: 'rgba(254, 90, 63, 0.1)',
                    label: {
                        text: 'Torrential',
                        align: 'right',
                        verticalAlign: 'top',
                        x: 60,
                        y: 10
                    }""")

        chart_file.write("""
                }]
            }]""")

        chart_file.write(""",
            series: [{""")

        if _disc_gage_info['sensor'].data():
            # Write actual waterlevel data
            chart_file.write("""
                name: 'Actual',
                type: 'spline',
                tooltip: {
                    valueSuffix: ' m'
                },
                data: [
                    """)
            chart_file.write(_data_writer(_disc_gage_info['sensor'].data()))
            chart_file.write("""
                ]""")
            chart_file.write("""
            }, {""")

        # Write predicted waterlevel data
        if not testing:
            counter = len(_release_trans)
            if not show_old_predicted:
                counter -= 1
        else:
            counter = len(_disc_gage_info['predicted']['waterlevel'])

        # _logger.debug('testing = %s', testing)

        for series_key, data in \
                sorted(_disc_gage_info['predicted']['waterlevel'].viewitems()):

            # _logger.debug('series_key = %s', series_key)

            if (testing or series_key in _release_trans.viewvalues()):

                if ((series_key == 'Old Predicted' and show_old_predicted) or
                        series_key != 'Old Predicted'):

                    chart_file.write("""
                            name: """)

                    if not testing:
                        for k, v in _release_trans.viewitems():
                            if v == series_key:
                                break
                        chart_file.write(
                            "'" + k + "',")
                    else:
                        chart_file.write("'" + series_key + "',")

                    chart_file.write("""
                            type: 'spline',
                            tooltip: {
                                valueSuffix: ' m'
                            },
                            data: [
                                """)

                    if (not testing and
                            _release_trans['Predicted'] == series_key):
                        wu = _current_time + \
                            _disc_gage_info['chart_options']['forecast_hours']
                        chart_file.write(_data_writer(data,
                                                      write_upto=wu))
                    else:
                        chart_file.write(_data_writer(data))

                    chart_file.write("""
                            ]""")

                    counter -= 1

                    if counter != 0:
                        chart_file.write("""
                        }, {""")

        # Write rainfall data
        for prec_gage, prec_gage_info in \
                sorted(_HECHMS_CONFIG.prec_gages.viewitems()):

            counter = len(prec_gage_info['cumulative'])

            for cumhr, data in prec_gage_info['cumulative'].viewitems():

                chart_file.write("""
                }, {
                    name: """)

                chart_file.write("'" +
                                 prec_gage_info['sensor'].meta()['location'] +
                                 ' (' + str(cumhr) + "hr cum)',")

                chart_file.write("""
                    type: 'column',""")

                chart_file.write("""
                    pointRange: """ + str(60 * 60 * 1000) + """,""")

                chart_file.write("""
                    tooltip: {
                        valueSuffix: ' mm/hr'
                    },
                    yAxis: 1,""")

                if cumhr == 3:
                    chart_file.write("""
                    visible: true,""")
                else:
                    chart_file.write("""
                    visible: false,""")

                chart_file.write("""
                    data: [
                        """)

                chart_file.write(_data_writer(data))

                chart_file.write("""
                        ]""")

                counter -= 1

        chart_file.write("""
            }]""")

        chart_file.write("""
        });
    });
        </script>
    </head>
    <body>
<script src="js/highstock.js"></script>
<script src="js/modules/exporting.js"></script>

<div id="container" style="height: 600px; min-width: 500px"></div>

    </body>
</html>""")


def _data_writer(data, write_upto=None):
    buf = []
    for t, v in sorted(data.viewitems()):
        if write_upto and t <= write_upto:
            # Format time
            line = '[' + _utc_format(t) + ', '
            # Format v
            line += '%.3f' % v
            line += ']'
            buf.append(line)
    return ',\n\t\t\t\t\t'.join(buf)


def _utc_format(t):
    return ('Date.UTC(' + str(t.year) + ', ' + str(t.month - 1) + ', ' +
            str(t.day) + ', ' + str(t.hour) + ', ' + str(t.minute) +
            ')')

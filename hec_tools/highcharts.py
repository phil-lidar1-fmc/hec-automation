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

from pprint import pformat
import os
import os.path as op
import logging

_version = '2.9'
print(os.path.basename(__file__) + ': v' + _version)
_logger = logging.getLogger()
_rainfall_palettes = {1: '34,102,102,1',
                      3: '46,66,114,.9',
                      6: '64,48,117,.8',
                      12: '88,42,114,.7',
                      24: '136,45,97,.6'}


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
    _ismsl = '(non-MSL)'
    if 'msl' in _disc_gage_info['sensor'].data_type():
        _ismsl = '(MSL)'

    # Get chart file path
    chart_fp = op.join(_MAIN_CONFIG.charts_dir,
                       _sanitize(_location))

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

        chart_file.write(_location + ' ' + _ismsl + ' @' +
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

        chart_file.write("'" + _location + ' ' + _ismsl + ' @' +
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
                        text: '(Light)',
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
                        text: '(Moderate)',
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
                        text: '(Heavy)',
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
                        text: '(Intense)',
                        align: 'right',
                        verticalAlign: 'top',
                        x: -60,
                        y: 10
                    }""")

        chart_file.write("""
                }, { // Torrential
                    from: 30,
                    to: 9999,
                    color: 'rgba(254, 90, 63, 0.1)',
                    label: {
                        text: '(Torrential)',
                        align: 'right',
                        verticalAlign: 'top',
                        x: -60,
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
        _waterlevel_data = _disc_gage_info['predicted']['waterlevel']
        if not testing:
            counter = len(_release_trans)
            if not show_old_predicted:
                counter -= 1
        else:
            counter = len(_waterlevel_data)

        # _logger.debug('testing = %s', testing)

        for series_key, data in sorted(_waterlevel_data.viewitems()):

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
                        chart_file.write(_data_writer(data, False))
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


def _data_writer(data, write_all=True):
    buf = []
    for t, v in sorted(data.viewitems()):
        if (not write_all and t >= _current_time) or write_all:
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

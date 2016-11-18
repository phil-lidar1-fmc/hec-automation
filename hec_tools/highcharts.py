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


def write_chart(waterlevel_data, rainfall_data, wl_name_base, chart_subtitle,
                current_time, start_time, end_time, dest_dir, testing,
                release_trans, min_waterlevel, max_waterlevel):
    # Water level and rainfall combined in one chart
    # Set global parameters
    global _waterlevel_data
    _waterlevel_data = waterlevel_data
    global _rainfall_data
    _rainfall_data = rainfall_data
    global _waterlevel_name_base
    _waterlevel_name_base = wl_name_base
    global _chart_subtitle
    _chart_subtitle = chart_subtitle
    global _current_time
    _current_time = current_time
    global _start_time
    _start_time = start_time
    global _end_time
    _end_time = end_time
    global _release_trans
    _release_trans = release_trans
    global _min_waterlevel
    _min_waterlevel = min_waterlevel
    global _max_waterlevel
    _max_waterlevel = max_waterlevel
    # Get chart file path
    chart_file_name = op.join(dest_dir,
                              wl_name_base.replace(' ', '_').replace(',', ''))
#     if testing:
#         # If testing, write only the debug chart
#         write_html(chart_file_name + '.html', testing=True, use_minmax=False)
# #        write_html(chart_file_name + '.html', testing, True)
#     else:
    # If live, write the release and the debug chart
    write_html(chart_file_name + '.html')
    write_html(chart_file_name + '_pagasa.html', show_old_predicted=True)
    write_html(chart_file_name + '_debug.html', testing=True, use_minmax=False,
               show_old_predicted=True)


def write_html(chart_file_path, testing=False, use_minmax=False,
               show_old_predicted=False):
    # Write chart html file
    with open(chart_file_path, 'w') as chart_file:
        chart_file.write("""
<!DOCTYPE HTML>
<html>
    <head>
        <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
        <title>""")
        chart_file.write(_waterlevel_name_base)
        chart_file.write("""</title>
        <script type="text/javascript" \
src="js/jquery.1.8.2.min.js"></script>
        <script type="text/javascript">
$(function () {
        $('#container').highcharts('StockChart', {
            chart: {
                zoomType: 'x'
            },""")
        if testing:
            chart_file.write("""
            subtitle: {
                text: '""")
            chart_file.write(_chart_subtitle)
            chart_file.write("""'
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
        chart_file.write("'" + _waterlevel_name_base + ' @' +
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
        if use_minmax:
            chart_file.write(""",
                min: """)
            chart_file.write(str(_min_waterlevel))
            chart_file.write(""",
                max: """)
            chart_file.write(str(_max_waterlevel))
            chart_file.write(""",""")
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
                        return this.value +' mm/hr';
                    },
                    style: {
                        color: '#4572A7'
                    },
                    y: 12
                },
                reversed: true,
                opposite: true,
                min: 0,""")
        if use_minmax:
            chart_file.write("""
                max: 80,""")
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
        # Write waterlevel data
        if not testing:
            counter = len(_release_trans)
            if not show_old_predicted:
                counter -= 1
        else:
            counter = len(_waterlevel_data)
        for k, v in sorted(_waterlevel_data.items()):
            # if (not testing and k in _release_trans) or testing:
            #     if ((not show_old_predicted and k == 'Old Predicted') or
            #             show_old_predicted):
            if (testing or k in _release_trans):
                if ((k == 'Old Predicted' and show_old_predicted) or
                        k != 'Old Predicted'):
                    chart_file.write("""
                            name: """)
                    if not testing:
                        chart_file.write("'" + _release_trans[k] + "',")
                    else:
                        chart_file.write("'" + k + "',")
                    chart_file.write("""
                            type: 'spline',
                            tooltip: {
                                valueSuffix: ' m'
                            },
                            data: [
                                """)
                    _logger.debug('k = %s', k)
                    _logger.debug('testing = %s', testing)
                    if not testing and _release_trans[k] == 'Predicted':
                        chart_file.write(_data_writer(v, False))
                    else:
                        chart_file.write(_data_writer(v))
                    chart_file.write("""
                            ]""")
                    counter -= 1
                    if counter != 0:
                        chart_file.write("""
                        }, {""")
        # Write rainfall data
        # counter = len(_rainfall_data)
        # for k, v in sorted(_rainfall_data.items()):
            # if counter != 0:
            #     chart_file.write("""
            # }, {""")
        #     chart_file.write("""
        #         name: """)
        #     chart_file.write("'" + k + "',")
        #     chart_file.write("""
        #         type: 'column',
        #         tooltip: {
        #             valueSuffix: ' mm/hr'
        #         },
        #         yAxis: 1,
        #         data: [
        #             """)
        #     chart_file.write(_data_writer(v))
        #     chart_file.write("""
        #         ]""")
        #     counter -= 1
        chart_file.write("""
            }, {""")
        for k1, v1 in sorted(_rainfall_data.viewitems()):
            # if (not testing and k in _release_trans) or testing:
            #     if ((not show_old_predicted and k == 'Old Predicted') or
            #             show_old_predicted):
            counter = len(v1)
            for k2, v2 in sorted(v1.viewitems()):
                # if counter != 0:
                #     chart_file.write("""
                # }, {""")
                chart_file.write("""
                    name: """)
                chart_file.write("'" + k2 + ' (' + str(k1) + "hr cum)',")
                # chart_file.write("""
                #     color: 'rgba(""" + _rainfall_palettes[k1] + """)',""")
                chart_file.write("""
                    type: 'column',""")
                chart_file.write("""
                    pointRange: """ + str(60 * 60 * 1000) + """,""")
                chart_file.write("""
                    tooltip: {
                        valueSuffix: ' mm/hr'
                    },
                    yAxis: 1,""")
                if k1 == 3:
                    chart_file.write("""
                    visible: true,""")
                else:
                    chart_file.write("""
                    visible: false,""")
                chart_file.write("""
                    data: [
                        """)
                chart_file.write(_data_writer(v2))
                chart_file.write("""
                        ]""")
                counter -= 1
                if counter != 0:
                    chart_file.write("""
                    }, {""")
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
    for time, value in sorted(data.items()):
        if (not write_all and time >= _current_time) or write_all:
            # Format time
            line = '[' + _utc_format(time) + ', '
            # Format value
            line += '%.3f' % value
            line += ']'
            buf.append(line)
    return ',\n\t\t\t\t\t'.join(buf)


def _utc_format(time):
    return ('Date.UTC(' + str(time.year) + ', ' + str(time.month - 1) + ', ' +
            str(time.day) + ', ' + str(time.hour) + ', ' + str(time.minute) +
            ')')

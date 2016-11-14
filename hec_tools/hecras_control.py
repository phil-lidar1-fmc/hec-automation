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

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS 'AS IS' AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

Acknowledgements:
- Jen Alconis (jen@noah.dost.gov.ph) for the douglas_peucker function
'''

from datetime import datetime
from pykml import parser as pykml_parser
import logging
import lxml
import main_control
import math
import os
import os.path as op
import pywinauto as pwa
import shutil
import subprocess
import time

_version = '2.26'
print(os.path.basename(__file__) + ': v' + _version)
_logger = logging.getLogger()
_PWA_TIMEOUT = 180  # seconds
_DEVNULL = open(os.devnull, 'w')


def hecras_control(current_time, main_config, hecras_config, series_info):
    hechms_start = datetime.now()
    _logger.info('hechms_start = %s', hechms_start)
    # Initialize HEC-RAS
    _logger.info('Initializing HEC-RAS...')
    initialize_hecras(current_time, main_config, hecras_config, series_info)
    # Run HEC-RAS
    _logger.info('Running HEC-RAS...')
    try:
        run_hecras()
    except Exception:
        _logger.exception('Error while running HEC-RAS!')
        raise
    # Convert shapefiles to kmz
    _logger.info('Converting shapefiles to kmz...')
    shp2kmz(current_time)
    hecras_end = datetime.now()
    _logger.info('hecras_end = %s', hecras_end)
    _logger.info('hecras_duration = %s', hecras_end - hechms_start)


def initialize_hecras(current_time, main_config, hecras_config, series_info):
    _logger.debug('series_info = %s', series_info)
    # Set global parameters
    _logger.info('Setting global parameters...')
    global _MAIN_CONFIG
    _MAIN_CONFIG = main_config
    global _HECRAS_CONFIG
    # if edits are made to this variable, consider copying
    _HECRAS_CONFIG = hecras_config
    #
    # Get simulation end time based on last data on the dss file
    _logger.info('Getting simulation end time...')
    end_time = series_info['dss_info'].end_time
    _logger.debug('end_time = %s', end_time)
    # Update simulation date
    _logger.info('Updating simulation date...')
    # Read plan file into buffer and update simulation date
    _logger.info('Reading plan file into buffer and updating simulation \
date...')
    buf = []
    for _, line in main_control.text_file_line_gen(_HECRAS_CONFIG.plan_file):
        if 'Simulation Date' in line:
            buf.append('Simulation Date=' +
                       current_time.strftime('%d%b%Y,%H:%M,').upper() +
                       end_time.strftime('%d%b%Y,%H:%M').upper())
        else:
            buf.append(line)
    # Write new plan file
    _logger.info('Writing new plan file...')
    with open(_HECRAS_CONFIG.plan_file, 'w') as open_file:
        open_file.write('\n'.join(buf))
    # Update dss file info
    _logger.info('Updating dss file info...')
    # Read unsteady flow file into buffer and update dss file info
    _logger.info('Reading unsteady flow file into buffer and updating dss \
file info...')
    buf = []
    for _, line in main_control.text_file_line_gen(
            _HECRAS_CONFIG.unsflow_file):
        if 'DSS File' in line:
            buf.append('DSS File=' + op.relpath(series_info['dss_file'],
                                                _HECRAS_CONFIG.hecras_proj_dir))
            _logger.debug(buf[-1])
        elif 'DSS Path' in line:
            buf.append('DSS Path=' + series_info['dss_info'].fullName)
        elif 'Use DSS' in line:
            buf.append('Use DSS=True')
        else:
            buf.append(line)
    # Write new unsteady flow file
    _logger.info('Writing new unsteady flow file...')
    with open(_HECRAS_CONFIG.unsflow_file, 'w') as open_file:
        open_file.write('\n'.join(buf))
    # Delete contents of flood mapping shapefile directory
    _logger.info('Cleaning up flood mapping shapefile directory...')
    for content in sorted(os.listdir(_HECRAS_CONFIG.flood_map_dir)):
        content_path = op.join(_HECRAS_CONFIG.flood_map_dir, content)
        if op.isdir(content_path):
            _logger.info('Deleting directory: %s', content)
            shutil.rmtree(content_path)
        elif op.isfile(content_path) and not content.startswith('.'):
            _logger.info('Deleting file: %s', content)
            os.remove(content_path)


def run_hecras():
    # Launch HEC-RAS
    _logger.info('Launching HEC-RAS...')
    hecras = subprocess.Popen([_MAIN_CONFIG.hecras_exe,
                               _HECRAS_CONFIG.hecras_proj_file])
    try:
        # Use pywinauto to control HEC-RAS gui
        _logger.info('Using pywinauto to control HEC-RAS gui...')
        app = pwa.Application()
        hecras_window = pwa.timings.WaitUntilPasses(_PWA_TIMEOUT, 0.5,
                                                    lambda: app.window_(title='HEC-RAS 4.1.0'))
        pwa.timings.WaitUntilPasses(_PWA_TIMEOUT, 0.5,
                                    lambda: hecras_window.SetFocus())
        # Run unsteady flow analysis
        _logger.info('Running unsteady flow analysis...')
        pwa.timings.WaitUntilPasses(_PWA_TIMEOUT, 0.5,
                                    lambda: hecras_window.MenuItem('&Run->&Unsteady Flow Analysis ...').Click())
        unsteady_flow_window = pwa.timings.WaitUntilPasses(_PWA_TIMEOUT, 0.5,
                                                           lambda: app.window_(title='Unsteady Flow Analysis'))
        pwa.timings.WaitUntilPasses(_PWA_TIMEOUT, 0.5,
                                    lambda: unsteady_flow_window.SetFocus())
        pwa.timings.WaitUntilPasses(_PWA_TIMEOUT, 0.5,
                                    lambda: unsteady_flow_window['Compute'].Click())
        # Wait for computation to finish
        _logger.info('Waiting for computation to finish...')
        hecras_comps_window = pwa.timings.WaitUntilPasses(_PWA_TIMEOUT, 0.5,
                                                          lambda: app.window_(title='HEC-RAS Finished Computations'))
        pwa.timings.WaitUntilPasses(_PWA_TIMEOUT, 0.5,
                                    lambda:  hecras_comps_window.SetFocus())
        pwa.timings.WaitUntilPasses(_PWA_TIMEOUT, 0.5,
                                    lambda: hecras_comps_window['Close'].Click())
        pwa.timings.WaitUntilPasses(_PWA_TIMEOUT, 0.5,
                                    lambda:  unsteady_flow_window.Close())
        # Run RAS Mapper
        _logger.info('Running RAS Mapper...')
        pwa.timings.WaitUntilPasses(_PWA_TIMEOUT, 1,
                                    lambda: hecras_window.MenuItem('&GIS Tools->RAS Mapper ...').Click())
        ras_mapper_window = pwa.timings.WaitUntilPasses(_PWA_TIMEOUT, 0.5,
                                                        lambda: app.window_(title='RAS Mapper'))
        pwa.timings.WaitUntilPasses(_PWA_TIMEOUT, 0.5,
                                    lambda:  ras_mapper_window.SetFocus())
        # Run Floodplain Mapping
        _logger.info('Running Floodplain Mapping...')
        pwa.timings.WaitUntilPasses(_PWA_TIMEOUT, 0.5,
                                    lambda:  ras_mapper_window['MenuStrip1'].TypeKeys('%tf'))
        flood_map_window = pwa.timings.WaitUntilPasses(_PWA_TIMEOUT, 0.5,
                                                       lambda: app.window_(title='Floodplain Mapping'))
        pwa.timings.WaitUntilPasses(_PWA_TIMEOUT, 0.5,
                                    lambda:  flood_map_window.SetFocus())
        # Select Max WS and current time under Profiles
        _logger.info('Selecting Max WS and current time under Profiles...')
        pwa.timings.WaitUntilPasses(_PWA_TIMEOUT, 0.5,
                                    lambda: flood_map_window['ListBox2'].Select(1))
        pwa.timings.WaitUntilPasses(_PWA_TIMEOUT, 2,
                                    lambda: flood_map_window['Button7'].Click())
        # Wait for layer generation to finish
        _logger.info('Waiting for layer generation to finish...')
        pwa.timings.WaitUntilPasses(_PWA_TIMEOUT, 2,
                                    lambda: pwa.findwindows.find_windows(title=u'RAS Mapper',
                                                                         class_name='#32770')[0])
        ras_mapper_dialog = pwa.timings.WaitUntilPasses(_PWA_TIMEOUT, 2,
                                                        lambda: app.top_window_())
        pwa.timings.WaitUntilPasses(_PWA_TIMEOUT, 2,
                                    lambda: ras_mapper_dialog.SetFocus())
        pwa.timings.WaitUntilPasses(_PWA_TIMEOUT, 2,
                                    lambda: ras_mapper_dialog['OK'].Click())
    except Exception as e:
        # Restart Windows
        # _logger.info('Restarting Windows...')
        # subprocess.call(['shutdown', '/r'])
        _logger.exception('Error running HEC-RAS!')
        exit(1)
    finally:
        # Terminate HEC-RAS
        _logger.info('Terminating HEC-RAS...')
        hecras.terminate()
        time.sleep(.5)


def shp2kmz(current_time):
    # Get contents of flood mapping shapefile directory
    _logger.info('Getting contents of flood mapping shapefile directory...')
    for content in sorted(os.listdir(_HECRAS_CONFIG.flood_map_dir)):
        # Go into each subdirectory
        content_path = op.join(_HECRAS_CONFIG.flood_map_dir, content)
        if op.isdir(content_path):
            _logger.info('Processing: %s', content)
            # Get shapefile path
            shapefile = op.realpath(op.join(content_path, 'floodmap.shp'))
            # Check if it exists
            main_control.is_exists(shapefile)
            _logger.debug('shapefile = %s', shapefile)
            # Get kml input file path
            kml_in = op.realpath(op.join(content_path, 'floodmap.kml'))
            _logger.debug('kml_in = %s', kml_in)
            # Convert shapefile to kml
            ogr2ogr = subprocess.Popen([_MAIN_CONFIG.ogr2ogr_exe,
                                        '-f', 'KML', kml_in, shapefile],
                                       stdout=_DEVNULL,
                                       stderr=subprocess.STDOUT)
            if ogr2ogr.wait() != 0:
                _logger.error('Error while running ogr2ogr.exe! Exiting.')
                exit(1)
            # Add name and description to placemark in kml file
            with open(kml_in, 'r') as f:
                # Parse kml file (convert file to kml object)
                doc = pykml_parser.parse(f)
                # Get document root
                root = doc.getroot()
                # Get placemark
                placemark = root.Document.Folder.Placemark
                # Set name of placeholder
                placemark.name = _HECRAS_CONFIG.kml_place_name
                if content == 'Max WS':
                    placemark.name += ' (Predicted maximum in 6 hours)'
                else:
                    placemark.name += ' (Current)'
                # Set description of placeholder
                placemark.description = content + ' Last updated: ' + \
                    current_time.strftime('%H:%M %p %B %d, %Y')
                # Set line color to blue
                line_style = placemark.Style.LineStyle
                line_style.color = 'ffff0000'
                # Perform smoothing algorithm on all polygons in
                # placemark
                if _HECRAS_CONFIG.smooth_algo:
                    try:
                        for mg in placemark.MultiGeometry.iterchildren():
                            for polygon in mg.iterchildren():
                                process_polygon(polygon)
                    except AttributeError:
                        for polygon in placemark.Polygon.iterchildren():
                            process_polygon(polygon)
            # Write changes to kml file
            with open(kml_in, 'w') as f:
                f.write(lxml.etree.tostring(doc, pretty_print=True))
            # Get target kml/kmz filename
            filename_base = op.basename(_HECRAS_CONFIG.kmz_output_dir).lower()
            if content == 'Max WS':
                filename_head = filename_base + '-max-rivermap.'

            else:
                filename_head = filename_base + '-cur-rivermap.'
            _logger.debug('filename_head = %s', filename_head)
            # Get kmz path
            kmz = op.realpath(op.join(_HECRAS_CONFIG.kmz_output_dir,
                                      filename_head + 'KMZ'))
            _logger.debug('kmz = %s', kmz)
            # Convert kml input file to kmz
            _7z = subprocess.Popen([_MAIN_CONFIG.p7z_exe, 'a', '-tzip',
                                    kmz + '.ZIP', kml_in], stdout=_DEVNULL,
                                   stderr=subprocess.STDOUT)
            # print(_MAIN_CONFIG.p7z_exe, 'a', '-tzip', '-aoa', kmz, kml_in)
            # _7z = subprocess.Popen([_MAIN_CONFIG.p7z_exe, 'a', '-tzip', '-aoa',
            #                         kmz, kml_in], stderr=subprocess.STDOUT)
            if _7z.wait() != 0:
                _logger.error('Error while running 7z.exe! Exiting.')
                exit(1)
            if op.isfile(kmz):
                os.remove(kmz)
            os.rename(kmz + '.ZIP', kmz)
            # Get kml output file path
            kml_out = op.realpath(op.join(_HECRAS_CONFIG.kmz_output_dir,
                                          filename_head + 'KML'))
            _logger.debug('kml_out = %s', kml_out)
            # Delete kml output file if it exists
            if op.isfile(kml_out):
                os.remove(kml_out)
            # Move kml input file to output directory
            os.rename(kml_in, kml_out)
            # Get shapefile filename
            shp_fn = filename_head[:-1] + '-shp.'
            # Get dest shapefile path
            shp_destpath = op.realpath(op.join(_HECRAS_CONFIG.kmz_output_dir,
                                               shp_fn + 'zip'))
            # Add shapefile to zip file
            _7z_shp_cmd = [_MAIN_CONFIG.p7z_exe, 'a', '-tzip',
                           shp_destpath, shapefile[:-4] + "*"]
            _7z_shp = subprocess.Popen(_7z_shp_cmd,
                                       stdout=_DEVNULL,
                                       stderr=subprocess.STDOUT)
            _logger.debug("_7z_shp = %s", " ".join(_7z_shp_cmd))
            if _7z_shp.wait() != 0:
                _logger.error('Error while running 7z.exe (_7z_shp)! Exiting.')
                exit(1)


def process_polygon(polygon):
    _logger.debug('polygon = %s', polygon.tag)
    # Extract point tuples
    points = []
    for point in str(polygon.LinearRing.coordinates).split():
        points.append(tuple([float(x)
                             for x in point.split(',')]))
    if _HECRAS_CONFIG.smooth_algo == 'DOP':
        # Running Douglas-Peucker algorithm
        new_points = douglas_peucker(points,
                                     _HECRAS_CONFIG.doug_peuc_tol)
    elif _HECRAS_CONFIG.smooth_algo == 'SMA':
        # Running simple moving average
        new_points = simple_moving_average(points,
                                           _HECRAS_CONFIG.sma_sample_size)
    # Set coordinates to new points
    new_points_string = [str(x) + ',' + str(y)
                         for (x, y) in new_points]
    polygon.LinearRing.coordinates = ' '.join(new_points_string)


def simple_moving_average(pts, sample_size=2.):
    new_pts = []
    xs = []
    ys = []
    while pts:
        x, y = pts.pop()
        xs.append(x)
        ys.append(y)
        if len(xs) >= sample_size or not pts:
            new_pts.append((sum(xs) / float(len(xs)),
                            sum(ys) / float(len(ys))))
            xs = []
            ys = []
    # Close the polygon
    new_pts.append(new_pts[0])
    return new_pts


def douglas_peucker(pts, tolerance):
    anchor = 0
    floater = len(pts) - 1
    stack = []
    keep = set()
    stack.append((anchor, floater))
    while stack:
        anchor, floater = stack.pop()
        # initialize line segment
        if pts[floater] != pts[anchor]:
            anchorX = float(pts[floater][0] - pts[anchor][0])
            anchorY = float(pts[floater][1] - pts[anchor][1])
            seg_len = math.sqrt(anchorX ** 2 + anchorY ** 2)
            # get the unit vector
            anchorX /= seg_len
            anchorY /= seg_len
        else:
            anchorX = anchorY = seg_len = 0.0
        # inner loop:
        max_dist = 0.0
        farthest = anchor + 1
        for i in range(anchor + 1, floater):
            dist_to_seg = 0.0
            # compare to anchor
            vecX = float(pts[i][0] - pts[anchor][0])
            vecY = float(pts[i][1] - pts[anchor][1])
            seg_len = math.sqrt(vecX ** 2 + vecY ** 2)
            # dot product:
            proj = vecX * anchorX + vecY * anchorY
            if proj < 0.0:
                dist_to_seg = seg_len
            else:
                # compare to floater
                vecX = float(pts[i][0] - pts[floater][0])
                vecY = float(pts[i][1] - pts[floater][1])
                seg_len = math.sqrt(vecX ** 2 + vecY ** 2)
                # dot product:
                proj = vecX * (-anchorX) + vecY * (-anchorY)
                if proj < 0.0:
                    dist_to_seg = seg_len
                else:
                    # calculate perpendicular distance to line
                    # (pythagorean theorem):
                    dist_to_seg = math.sqrt(abs(seg_len ** 2 - proj ** 2))
                if max_dist < dist_to_seg:
                    max_dist = dist_to_seg
                    farthest = i
        if max_dist <= tolerance:
            # use line segment
            keep.add(anchor)
            keep.add(floater)
        else:
            stack.append((anchor, farthest))
            stack.append((farthest, floater))
    keep = list(keep)
    keep.sort()
#    print 'Douglas-Peucker line simplification'
    return [pts[i] for i in keep]

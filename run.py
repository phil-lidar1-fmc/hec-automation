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

import os
import subprocess
import time

# Check if run dir exists
RUNDIR = os.path.abspath('run')
if os.path.isdir(RUNDIR):
    while True:
        count = 0.
        # List folder contents
        for c in os.listdir(RUNDIR):
            # Check if it's a batch file
            if c.endswith('.bat'):
                # Run batch file
                print '\n', '#' * 40, 'Running', c, '#' * 40, '\n'
                run = subprocess.Popen(os.path.join(RUNDIR, c), cwd=RUNDIR)
                run.wait()
                count += 1
        # Sleep for a set interval
        dur = 60 / count * 60
        print '\n', '#' * 40, 'Sleeping for', dur, 'secs', '#' * 40, '\n'
        time.sleep(dur)

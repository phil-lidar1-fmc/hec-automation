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

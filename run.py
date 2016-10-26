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
                print '#' * 40, 'Running', c, '#' * 40
                run = subprocess.Popen(os.path.join(RUNDIR, c), cwd=RUNDIR)
                run.wait()
                count += 1
        # Sleep for a set interval
        dur = 60 / count * 60
        print '#' * 40, 'Sleep for', dur, 'secs #' * 40
        time.sleep(dur)

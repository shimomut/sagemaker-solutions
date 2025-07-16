import os
import time
import datetime

output_dir = "/fsx/ubuntu/shutdown-action-data"

os.makedirs(output_dir, exist_ok=True)

t0 = datetime.datetime.now()

while True:
    t1 = datetime.datetime.now()
    if t1 - t0 > datetime.timedelta(minutes=3):
        break

    filename = t1.strftime("%Y%m%d_%H%M%S.txt")
    filepath = os.path.join(output_dir, filename)

    print("Writing", filepath)
    with open(filepath, "w") as fd:
        fd.close()

    time.sleep(5)

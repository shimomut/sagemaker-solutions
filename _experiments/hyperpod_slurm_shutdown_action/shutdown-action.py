import os
import time
import datetime
import logging
import traceback

output_dir = "/fsx/ubuntu/shutdown-action-logs"
duration_sec = 30 * 60

os.makedirs(output_dir, exist_ok=True)

t0 = datetime.datetime.now()

logger = logging.getLogger(__name__)

log_filename = t0.strftime(f"%Y%m%d_%H%M%S.log")
log_filepath = os.path.join(output_dir, log_filename)

logging.basicConfig(filename=log_filepath, level=logging.INFO)


def main():

    i = 0
    while True:
        t1 = datetime.datetime.now()

        elapsed_time = t1 - t0

        logger.info(f"Elapsed time: {elapsed_time}")

        if elapsed_time > datetime.timedelta(seconds=duration_sec):
            break

        time.sleep(1)

        i+=1

try:
    main()

except Exception as e:
    logger.error(f"Error: {str(e)}")
    logger.error("Stack trace: %s", traceback.format_exc())

logger.info("Finished")

time.sleep(3)

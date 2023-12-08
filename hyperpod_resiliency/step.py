#!/usr/bin/python3

import sys
import os
import time
import argparse

argparser = argparse.ArgumentParser(description='Test slurm step')
argparser.add_argument('--name', action='store', help='name of this task')
argparser.add_argument('--fail', action='store_true', help='exit with return code 1')
args = argparser.parse_args()


print(f"Running task [{args.name}]", flush=True)

time.sleep(10)

if args.fail:
    print(f"Task [{args.name}] failed.", flush=True)
    sys.exit(1)

print(f"Task [{args.name}] finished.", flush=True)

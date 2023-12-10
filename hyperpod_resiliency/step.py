#!/usr/bin/python3

import sys
import os
import time
import subprocess
import argparse

argparser = argparse.ArgumentParser(description='Test slurm step')
argparser.add_argument('--name', action='store', help='name of this task')
argparser.add_argument('--raise-exception', action='store_true', help='cause assetion failure')
argparser.add_argument('--gpu-failure', action='store_true', help='Simulate gpu failure and exit with return code 1')
args = argparser.parse_args()


print(f"[{args.name}] Running task", flush=True)

if 0:
    print(f"[{args.name}] Slurm related environment variables:", flush=True)
    for k in os.environ:
        if k.startswith("SLURM"):
            v = os.environ[k]
            print(f"  {k} : {v}", flush=True)

time.sleep(10)

if args.gpu_failure:

    if not os.path.exists("./gpu-failure-happened.txt"):

        if os.environ["SLURM_NODEID"] == "2":

            with open("./gpu-failure-happened.txt", "w") as fd:
                pass
        
            print(f"[{args.name}] Simulating GPU failure.", flush=True)

            # Some code to simulate GPU failure
            subprocess.run(["sudo", "python3", "simulate_gpu_failure.py"])

            sys.exit(1)

if args.raise_exception:
    assert False, f"[{args.name}] Simulating task failure"

print(f"[{args.name}] Finished.", flush=True)

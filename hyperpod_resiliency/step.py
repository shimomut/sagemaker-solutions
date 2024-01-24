#!/usr/bin/python3

import sys
import os
import time
import subprocess
import argparse

argparser = argparse.ArgumentParser(description='Test slurm step')
argparser.add_argument('--name', action='store', help='name of this task')
argparser.add_argument('--gpu-failure', action='store', help='Simulate gpu failure in the specified node (SLURM_NODEID) and exit with return code 1')
args = argparser.parse_args()

slurm_node_id = os.environ["SLURM_NODEID"]
slurm_job_id = os.environ["SLURM_JOB_ID"]
slurm_step_id = os.environ["SLURM_STEP_ID"]
slurm_local_id = os.environ["SLURM_LOCALID"]

print(f"[{args.name}] Running task : SLURM_NODEID={slurm_node_id} SLURM_JOB_ID={slurm_job_id} SLURM_STEP_ID={slurm_step_id} SLURM_LOCALID={slurm_local_id}", flush=True)

if 0:
    print(f"[{args.name}] Slurm related environment variables:", flush=True)
    for k in os.environ:
        if k.startswith("SLURM"):
            v = os.environ[k]
            print(f"  {k} : {v}", flush=True)

time.sleep(10)

if args.gpu_failure:

    if not os.path.exists("./gpu-failure-happened.txt"):

        if os.environ["SLURM_NODEID"] == args.gpu_failure:

            with open("./gpu-failure-happened.txt", "w") as fd:
                pass
        
            print(f"[{args.name}] Simulating GPU failure.", flush=True)

            # simulate GPU failure
            # https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/dcgm-error-injection.html#overview
            subprocess.run(["dcgmi", "test", "--inject", "--gpuid", "0", "-f", "319", "-v", "4"])

            sys.exit(1)

print(f"[{args.name}] Finished.", flush=True)

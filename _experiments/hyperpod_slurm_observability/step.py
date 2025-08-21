#!/usr/bin/python3

import os
import time
import argparse
import socket

argparser = argparse.ArgumentParser(description='Test slurm step')
argparser.add_argument('--name', action='store', help='name of this task')
args = argparser.parse_args()

slurm_node_id = os.environ["SLURM_NODEID"]
slurm_job_id = os.environ["SLURM_JOB_ID"]
slurm_step_id = os.environ["SLURM_STEP_ID"]
slurm_local_id = os.environ["SLURM_LOCALID"]
cuda_visible_devices = os.environ["CUDA_VISIBLE_DEVICES"]


print(f"[{args.name}] Running task : SLURM_NODEID={slurm_node_id} SLURM_JOB_ID={slurm_job_id} SLURM_STEP_ID={slurm_step_id} SLURM_LOCALID={slurm_local_id} CUDA_VISIBLE_DEVICES={cuda_visible_devices}", flush=True)

if 0:
    print(f"[{args.name}] Slurm related environment variables:", flush=True)
    for k in os.environ:
        if k.startswith("SLURM"):
            v = os.environ[k]
            print(f"  {k} : {v}", flush=True)

try:
    i = 0
    while True:
        ipaddr = socket.gethostbyname(socket.gethostname())

        print(f"{ipaddr}: Hello from Python script! - {i}", flush=True)

        time.sleep(10)
        i += 1

except Exception as e:
    print(e)

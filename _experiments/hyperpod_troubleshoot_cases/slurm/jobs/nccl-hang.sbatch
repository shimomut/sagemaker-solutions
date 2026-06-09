#!/bin/bash
#SBATCH -J hp-troubleshoot-case-5
#SBATCH -o output/case-5_%j.txt
#SBATCH -N 2
#SBATCH --ntasks-per-node=1
#SBATCH --gpus-per-node=1
#SBATCH --time=00:15:00

# Two-node NCCL AllReduce with deliberately mismatched WORLD_SIZE between
# ranks. Rank 0 thinks WORLD_SIZE=2, rank 1 thinks WORLD_SIZE=4 → NCCL init
# rendezvous never completes and the job hangs until the SBATCH time limit.
#
# This is a synthetic NCCL hang useful for testing hyperpod-nccl.

set -x
export NCCL_DEBUG=INFO
export NCCL_DEBUG_SUBSYS=INIT,COLL
export MASTER_ADDR=$(scontrol show hostnames "$SLURM_JOB_NODELIST" | head -n1)
export MASTER_PORT=29500

srun --kill-on-bad-exit=0 bash -c '
  if [ "$SLURM_PROCID" -eq 0 ]; then
    export WORLD_SIZE=2
  else
    export WORLD_SIZE=4
  fi
  export RANK=$SLURM_PROCID
  python3 -c "
import os, torch
import torch.distributed as dist
print(f\"rank={os.environ['RANK']} world_size={os.environ['WORLD_SIZE']}\", flush=True)
dist.init_process_group(backend=\"nccl\", init_method=\"env://\", timeout=__import__(\"datetime\").timedelta(minutes=10))
t = torch.ones(1, device=\"cuda\")
dist.all_reduce(t)
print(\"done\", t.item(), flush=True)
"
'

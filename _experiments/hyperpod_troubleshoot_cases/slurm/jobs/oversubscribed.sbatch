#!/bin/bash
#SBATCH -J hp-troubleshoot-case-2
#SBATCH -o output/case-2_%j.txt
#SBATCH -N __NODES__
#SBATCH --time=00:10:00

# Intentionally requests more nodes than the cluster has so the job sits
# PENDING with REASON=Resources. Used to test hyperpod-slurm-debugger.
srun hostname

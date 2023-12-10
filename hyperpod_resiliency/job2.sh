#!/bin/bash
#SBATCH -J job2
#SBATCH -o ./output/log_%j.txt
#SBATCH --time=1:00:00
#SBATCH --ntasks-per-node 1
#SBATCH -N 6
#SBATCH --exclusive

# This job requires memory setting in slurm.conf. See configs/slurm.conf.mem

# Auto-resume fails. ALways fails when modifying slurm.conf?
srun --nodes 6 --mem=100M --auto-resume=1 python3 step.py --name task1 --gpu-failure 1

# This also fails.
#srun --nodes 6 --auto-resume=1 python3 step.py --name task1 --gpu-failure 1

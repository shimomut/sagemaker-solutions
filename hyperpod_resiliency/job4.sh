#!/bin/bash
#SBATCH -J job2
#SBATCH -o ./output/log_%j.txt
#SBATCH --time=1:00:00
#SBATCH --ntasks-per-node 8
#SBATCH -N 6
#SBATCH --exclusive

# How about this?
srun --nodes 1 --ntasks 8 --auto-resume=1 python3 step.py --name task1

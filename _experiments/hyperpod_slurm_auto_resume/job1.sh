#!/bin/bash
#SBATCH -J job1
#SBATCH -o ./output/log_%j.txt
#SBATCH --time=1:00:00
#SBATCH --ntasks-per-node 1
#SBATCH -N 4
#SBATCH --exclusive

srun --nodes 4 --auto-resume=1 python3 -u step.py --name task1

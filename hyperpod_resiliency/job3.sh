#!/bin/bash
#SBATCH -J job2
#SBATCH -o ./output/log_%j.txt
#SBATCH --time=1:00:00
#SBATCH --ntasks-per-node 1
#SBATCH -N 6
#SBATCH --exclusive

# How about this?
srun --nodes 3 --auto-resume=1 python3 step.py --name task1 &
srun --nodes 3 --auto-resume=1 python3 step.py --name task1 --gpu-failure &
wait

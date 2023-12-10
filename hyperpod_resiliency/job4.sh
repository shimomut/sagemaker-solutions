#!/bin/bash
#SBATCH -J job4
#SBATCH -o ./output/log_%j.txt
#SBATCH --time=1:00:00
#SBATCH --ntasks-per-node 8
#SBATCH -N 3
#SBATCH --exclusive

# What if running multiple tasks on each node
srun --nodes 3 --ntasks 6 --auto-resume=1 python3 step.py --name task1 --gpu-failure 1

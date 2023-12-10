#!/bin/bash
#SBATCH -J job2
#SBATCH -o ./output/log_%j.txt
#SBATCH --time=1:00:00
#SBATCH --ntasks-per-node 1
#SBATCH -N 6
#SBATCH --exclusive

# Auto resume succeeds
#srun --nodes 6 --auto-resume=1 python3 step.py --name task1 --gpu-failure 

# Auto resume fails
#srun --nodes 6 --cpus-per-task=1 --auto-resume=1 python3 step.py --name task1 &

# How about this?
srun --nodes 6 --mem=100M --auto-resume=1 python3 step.py --name task1 &



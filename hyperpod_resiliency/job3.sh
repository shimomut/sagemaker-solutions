#!/bin/bash
#SBATCH -J job3
#SBATCH -o ./output/log_%j.txt
#SBATCH --time=1:00:00
#SBATCH --ntasks-per-node 1
#SBATCH -N 3
#SBATCH --exclusive

# Auto resume works at srun level. In this case only task2 re-runs.
srun --nodes 3 --auto-resume=1 python3 step.py --name task1 &
srun --nodes 3 --auto-resume=1 python3 step.py --name task2 --gpu-failure 1 &
wait

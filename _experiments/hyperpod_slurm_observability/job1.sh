#!/bin/bash
#SBATCH -J job1
#SBATCH -o ./output/log_%j.txt
#SBATCH --time=1:00:00
#SBATCH --ntasks-per-node 1
#SBATCH --gpus=5
#SBATCH -N 2
#SBATCH --exclusive

srun --nodes 2 python3 -u step.py --name task1

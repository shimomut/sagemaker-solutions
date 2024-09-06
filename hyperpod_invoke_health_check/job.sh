#!/bin/bash
#SBATCH -J invoke_health_check
#SBATCH -o ./output/log_%j.txt
#SBATCH --time=1:00:00
#SBATCH -N 2

srun --auto-resume=1 python3 step.py

#!/bin/bash
#SBATCH -J gres-test
#SBATCH -o ./output/log_%j.txt
#SBATCH --time=1:00:00
#SBATCH -N 1
#SBATCH --ntasks=1                  # Run a single task
#SBATCH --gres=gpu:1                # Request 1 GPU
#SBATCH --mem=4G                    # Memory needed

srun python3 step.py

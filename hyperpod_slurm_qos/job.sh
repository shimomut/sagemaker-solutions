#!/bin/bash
#SBATCH -J hello
#SBATCH -o ./output/log_%j.txt
#SBATCH --time=1:00:00
#SBATCH -N 1

srun -N 1 python3.9 hello.py

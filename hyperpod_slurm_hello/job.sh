#!/bin/bash
#SBATCH -J hello
#SBATCH -o ./output/log_%j.txt
#SBATCH --time=1:00:00
#SBATCH -N 2

srun -N 2 python3.9 hello.py

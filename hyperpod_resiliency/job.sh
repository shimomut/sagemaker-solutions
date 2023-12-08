#!/bin/bash
#SBATCH -J job1
#SBATCH -o ./output/log_%j.txt
#SBATCH --time=1:00:00
#SBATCH --ntasks-per-node 1
#SBATCH -N 2

#srun --nodes 1 --ntasks 1 --cpus-per-task=1 --auto-resume=1 python3 step.py --name task1 --raise-exception &
#srun --nodes 1 --ntasks 1 --cpus-per-task=1 --auto-resume=1 python3 step.py --name task2 &

srun --nodes 1 --ntasks 1 --cpus-per-task=1 --auto-resume=1 python3 step.py --name task1 --gpu-failure &
srun --nodes 1 --ntasks 1 --cpus-per-task=1 --auto-resume=1 python3 step.py --name task2 &

wait
